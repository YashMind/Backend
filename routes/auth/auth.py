from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
    Request,
    Response,
    Form,
    Query,
)
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from utils.utils import (
    create_access_token,
    decode_access_token,
    create_reset_token,
    get_timezone_from_ip,
    send_reset_email,
    decode_reset_access_token,
    get_current_user,
)
from jose import JWTError, jwt
from uuid import uuid4
import json
from models.authModel.authModel import AuthUser
from models.adminModel.roles_and_permission import RolePermission
from schemas.authSchema.authSchema import (
    PasswordChange,
    User,
    SignInUser,
    PasswordResetRequest,
    PasswordReset,
    UserUpdate,
)
from sqlalchemy.orm import Session
from config import get_db
from typing import Optional, Dict, List
from sqlalchemy import or_, desc, asc
from datetime import datetime
import httpx
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timedelta

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@router.get("/recent-signups")
async def get_recent_signups(db: Session = Depends(get_db)):
    try:
        # Calculate 24 hours ago from current UTC time
        since = datetime.utcnow() - timedelta(hours=24)

        # Fetch users created in the last 24 hours
        users = db.query(AuthUser).filter(AuthUser.created_at >= since).all()

        # Format the user data (you can customize fields as needed)
        user_list = [
            {
                "id": user.id,
                "fullName": user.fullName,
                "email": user.email,
                "created_at": user.created_at,
            }
            for user in users
        ]

        return {
            "success": True,
            "message": "Recent user signups in the last 24 hours.",
            "count": len(user_list),  # Include total count
            "data": user_list,
        }

    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")


@router.post("/signup")
async def signup(user: User, db: Session = Depends(get_db)):
    try:
        fullName = user.fullName
        email = user.email
        password = user.password
        role = user.role if user.role else "user"
        status = user.status if user.status else None
        role_permissions = user.role_permissions if user.role_permissions else None
        base_rate_per_token = (
            user.base_rate_per_token if user.base_rate_per_token else None
        )
        if not fullName or not email or not password:
            raise HTTPException(
                status_code=400, detail="email and password are required"
            )
        hashed_password = pwd_context.hash(user.password)
        existing_user = db.query(AuthUser).filter(AuthUser.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="ERR_ALREADY_EXIST")

        new_user = AuthUser(
            fullName=fullName,
            email=email,
            password=hashed_password,
            role=role,
            status=status,
            role_permissions=role_permissions,
            base_rate_per_token=base_rate_per_token,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {"message": "User created successfully"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/signin")
async def signin(
    request: Request,
    user: SignInUser,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        print(user, "===========")
        if not user.email or not user.password:
            raise HTTPException(
                status_code=400, detail="Email and password are required"
            )

        db_user = db.query(AuthUser).filter(AuthUser.email == user.email).first()

        if not db_user:
            raise HTTPException(status_code=400, detail="Email is incorrect")

        if not pwd_context.verify(user.password, db_user.password):
            raise HTTPException(status_code=400, detail="Password is incorrect")

        if not db_user.fullName or not db_user.role:
            raise HTTPException(status_code=400, detail="Incomplete user data")

        access_token = create_access_token(
            data={
                "sub": db_user.email,
                "user_id": str(db_user.id),
                "username": db_user.fullName,
                "role": db_user.role,
            }
        )

        client_ip = request.client.host
        timezone = await get_timezone_from_ip(ip=client_ip)

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="Lax",
            # max_age=84600,
        )
        response.set_cookie(
            key="role",
            value=db_user.role,
            httponly=False,
            secure=False,
            samesite="Lax",
            # max_age=84600,
        )

        response.set_cookie(
            key="timezone",
            value=timezone,
            httponly=False,
            secure=False,
            samesite="Lax",
            # max_age=84600,
        )

        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


@router.get("/me")
async def getme(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        if not token:
            response.delete_cookie("access_token")
            response.delete_cookie("role")
            raise HTTPException(status_code=401, detail="Not authenticated")

        payload = decode_access_token(token)
        user_id = payload.get("user_id")
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if not user:
            response.delete_cookie("access_token")
            response.delete_cookie("role")
            raise HTTPException(status_code=400, detail="User not found")

        user.last_active = datetime.utcnow()

        db.commit()
        db.refresh(user)
        del user.facebookId
        del user.googleId
        del user.password

        return {"user": user, "status": 200}

    except HTTPException as http_exc:
        error_response = JSONResponse(
            content={"detail": http_exc.detail}, status_code=http_exc.status_code
        )
        error_response.delete_cookie("access_token")
        error_response.delete_cookie("role")
        return error_response


@router.post("/forget-password")
async def forget_password(
    request: PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        user = db.query(AuthUser).filter(AuthUser.email == request.email).first()
        if not user:
            raise HTTPException(
                status_code=404, detail="User with this email does not exist"
            )

        reset_token = create_reset_token({"sub": str(user.id)})
        background_tasks.add_task(send_reset_email, request.email, reset_token)

        return {"message": "Password reset email sent"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/reset-password")
async def reset_password(data: PasswordReset, db: Session = Depends(get_db)):
    try:
        user_id = decode_reset_access_token(data.token)
        if user_id is None:
            raise HTTPException(status_code=400, detail="Invalid token")
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        hashed_password = pwd_context.hash(data.new_password)
        user.password = hashed_password
        db.commit()

        return {"message": "Password reset successful"}
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid token")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/change-password")
async def reset_password(
    request: Request, data: PasswordChange, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)

        print(payload)
        if payload.get("user_id") is None:
            raise HTTPException(status_code=400, detail="Invalid token")
        user = db.query(AuthUser).filter(AuthUser.id == payload.get("user_id")).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_password = data.old_password
        if not pwd_context.verify(old_password, user.password):
            raise HTTPException(status_code=400, detail="Current Password is incorrect")

        hashed_password = pwd_context.hash(data.new_password)
        user.password = hashed_password
        db.commit()

        return {"message": "Password changed successful"}
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid token")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# current_user: dict = Depends(get_current_user)
@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    try:
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="role")
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during logout",
        ) from e


@router.put("/update-profile")
async def update_profile(
    updateUser: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # Get the user from database
        user = db.query(AuthUser).filter(AuthUser.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Define editable fields and their validation rules
        editable_fields = {
            "fullName": {"type": str, "max_length": 100},
            "isMFA": {"type": bool},
            "tokenUsed": {"type": int},
            "picture": {"type": str},  # Assuming this is a URL after upload
        }

        # Track changes for audit logging
        changes = {}

        # Process each editable field
        for field, rules in editable_fields.items():
            if field in updateUser.dict() and updateUser.dict()[field] is not None:
                # Validate field type
                if not isinstance(updateUser.dict()[field], rules["type"]):
                    try:
                        # Attempt type conversion if possible
                        updateUser.dict()[field] = rules["type"](
                            updateUser.dict()[field]
                        )
                    except (ValueError, TypeError):
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid type for {field}. Expected {rules['type'].__name__}",
                        )

                # Additional validation based on field rules
                if (
                    rules.get("max_length")
                    and len(str(updateUser.dict()[field])) > rules["max_length"]
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"{field} exceeds maximum length of {rules['max_length']}",
                    )

                # Only update if the value actually changed
                if getattr(user, field) != updateUser.dict()[field]:
                    changes[field] = {
                        "old": getattr(user, field),
                        "new": updateUser.dict()[field],
                    }
                    setattr(user, field, updateUser.dict()[field])

        # Special handling for password changes
        if updateUser.password:
            if len(updateUser.password) < 8:
                raise HTTPException(
                    status_code=400,
                    detail="Password must be at least 8 characters long",
                )
            hashed_pw = pwd_context.hash(updateUser.password)
            changes["password"] = {"changed": True}  # Don't log actual passwords
            user.password = hashed_pw

        # If no changes were made
        if not changes and not updateUser.password:
            raise HTTPException(status_code=304, detail="No changes detected")

        # Commit changes to database
        db.commit()
        db.refresh(user)

        # Log the changes (you'd implement your own logging system)
        # log_profile_update(current_user.id, changes)

        return {
            "status": "success",
            "message": "Profile updated successfully",
            "updated_fields": list(changes.keys()),
        }

    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        db.rollback()
        print(f"Error updating profile: {str(e)}")
        raise HTTPException(
            status_code=500, detail="An error occurred while updating the profile"
        )


# google login
@router.post("/google-login")
async def google_login(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    try:
        data = await request.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token missing")

        async with httpx.AsyncClient() as client:
            res = await client.get(
                GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {token}"}
            )
            if res.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch user info")

            user_data = res.json()
            print("user data ", user_data)
            email = user_data.get("email")
            name = user_data.get("name")
            googleId = user_data.get("id")
            picture = user_data.get("picture")
            if not email:
                raise HTTPException(
                    status_code=400, detail="Email not found in Google response"
                )
            user = db.query(AuthUser).filter(AuthUser.email == email).first()
            print("user ", user)
            dummy_password = pwd_context.hash("GOOGLE_AUTH_NO_PASSWORD")
            if not user:
                user = AuthUser(
                    email=email,
                    fullName=name,
                    password=dummy_password,
                    provider="google",
                    googleId=googleId,
                    picture=picture,
                )
                db.add(user)
                db.commit()
                db.refresh(user)

            access_token = create_access_token(
                data={"sub": email, "user_id": str(user.id), "role": user.role}
            )

            client_ip = request.client.host
            timezone = await get_timezone_from_ip(ip=client_ip)

            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=False,
                samesite="Lax",
                # max_age=84600,
            )
            response.set_cookie(
                key="role",
                value=user.role,
                httponly=False,
                secure=False,
                samesite="Lax",
                # max_age=84600,
            )
            response.set_cookie(
                key="timezone",
                value=timezone,
                httponly=False,
                secure=False,
                samesite="Lax",
                # max_age=84600,
            )
            return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/facebook-login")
async def facebook_login(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    try:
        data = await request.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token missing")

        # Facebook Graph API endpoint to get user info
        facebook_url = "https://graph.facebook.com/me"
        params = {"fields": "id,name,email,picture", "access_token": token}

        async with httpx.AsyncClient() as client:
            res = await client.get(facebook_url, params=params)

        if res.status_code != 200:
            print("Facebook error response:", res.text)
            raise HTTPException(
                status_code=400, detail="Failed to fetch user info from Facebook"
            )

        user_data = res.json()
        email = user_data.get("email")
        name = user_data.get("name")
        facebookId = user_data.get("id")
        picture = user_data.get("picture")

        if not email:
            raise HTTPException(
                status_code=400, detail="Email not found in Facebook response"
            )

        user = db.query(AuthUser).filter(AuthUser.email == email).first()
        if not user:
            dummy_password = pwd_context.hash("FACEBOOK_AUTH_NO_PASSWORD")
            user = AuthUser(
                email=email,
                fullName=name,
                password=dummy_password,
                provider="facebook",
                facebookId=facebookId,
                picture=picture,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        access_token = create_access_token(
            data={"sub": email, "user_id": str(user.id), "role": user.role}
        )
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="Lax",
            # max_age=3600,
        )

        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
