from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response, Form, Query
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from utils.utils import create_access_token, decode_access_token, create_reset_token, send_reset_email, decode_reset_access_token, get_current_user
from jose import JWTError, jwt
from uuid import uuid4
import json
from models.authModel.authModel import AuthUser
from schemas.authSchema.authSchema import User, SignInUser, PasswordResetRequest, PasswordReset, UserUpdate
from sqlalchemy.orm import Session
from config import get_db
from typing import Optional, Dict, List
from sqlalchemy import or_, desc, asc
from datetime import datetime
import httpx
router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

@router.post("/signup")
async def signup(user: User, db: Session = Depends(get_db)):
    try:
        fullName = user.fullName
        email = user.email
        password = user.password
        role = user.role
        status = user.status if user.status else None
        role_permissions = user.role_permissions if user.role_permissions else None
        if not fullName or not email or not password:
            raise HTTPException(status_code=400, detail="email and password are required")
        hashed_password = pwd_context.hash(user.password)
        existing_user = db.query(AuthUser).filter(AuthUser.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="email already registered")

        new_user = AuthUser(
            fullName=fullName,
            email=email,
            password=hashed_password,
            role=role,
            status=status,
            role_permissions=role_permissions
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
async def signin(user: SignInUser, response: Response, db: Session = Depends(get_db)):
    try:
        email = user.email
        password = user.password
        if not email or not password:
            raise HTTPException(status_code=400, detail="Email and password are required")

        user = db.query(AuthUser).filter(AuthUser.email == email).first()
        if not user:
            raise HTTPException(status_code=400, detail="Incorrect email or password")
        is_valid_password = pwd_context.verify(password, user.password)
        if not is_valid_password:
            raise HTTPException(status_code=400, detail="Incorrect email or password")
        access_token = create_access_token(data={"sub": user.email, "user_id": str(user.id)})
        response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, 
                            samesite="Lax", max_age=84600)
        response.set_cookie(key="role", value=user.role, httponly=False, secure=False,samesite="Lax",max_age=84600)

        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error {e}")
    
@router.get("/me")
async def getme(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        payload = decode_access_token(token)
        user_id = payload.get("user_id")
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=400, detail="User not found")

        user.last_active = datetime.utcnow()

        db.commit()
        db.refresh(user)

        return {"user": user, "status": 200}

    except HTTPException as http_exc:
        if http_exc.status_code == 401:
            response = JSONResponse(
                content={"detail": "Invalid or expired token"},
                status_code=401
            )
            response.delete_cookie("access_token")
            return response
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/forget-password")
async def forget_password(request: PasswordResetRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        user =  db.query(AuthUser).filter(AuthUser.email == request.email).first()
        if not user:
            raise HTTPException(status_code=404, detail="User with this email does not exist")
        
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
        user = db.query(AuthUser).filter(AuthUser.id==user_id).first()
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

# current_user: dict = Depends(get_current_user)
@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    try:
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="role")
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during logout") from e

@router.put("/update-profile")
def update_profile(updateUser: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == current_user.id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if updateUser.fullName:
            user.fullName = updateUser.fullName

        if updateUser.password:
            hashed_pw = pwd_context.hash(updateUser.password)
            user.password = hashed_pw

        db.commit()
        db.refresh(user)

        return {
            "message": "Profile updated successfully",
            "user": {
                "id": user.id,
                "fullName": user.fullName,
                "email": user.email,
            },
        }
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

# google login
@router.post("/google-login")
async def google_login(request: Request, response:Response, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token missing")

        async with httpx.AsyncClient() as client:
            res = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {token}"})
            if res.status_code != 200:
                raise HTTPException(status_code=400, detail="Failed to fetch user info")

            user_data = res.json()
            print("user data ", user_data)
            email = user_data.get("email")
            name = user_data.get("name")
            googleId = user_data.get("id")
            picture = user_data.get("picture")
            if not email:
                raise HTTPException(status_code=400, detail="Email not found in Google response")
            user = db.query(AuthUser).filter(AuthUser.email == email).first()
            print("user ", user)
            dummy_password = pwd_context.hash("GOOGLE_AUTH_NO_PASSWORD")
            if not user:
                user = AuthUser(email=email, fullName=name, password=dummy_password, provider="google", googleId=googleId, picture=picture)
                db.add(user)
                db.commit()
                db.refresh(user)

            access_token = create_access_token(data={"sub": email, "user_id": str(user.id)})
            response.set_cookie(key="access_token", value=access_token, httponly=True, secure=False, 
                            samesite="Lax", max_age=84600)
            response.set_cookie(key="role", value=user.role, httponly=False, secure=False,samesite="Lax",max_age=84600)
            return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e)) from e
    
@router.post("/facebook-login")
async def facebook_login(request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        token = data.get("token")
        if not token:
            raise HTTPException(status_code=400, detail="Token missing")

        # Facebook Graph API endpoint to get user info
        facebook_url = "https://graph.facebook.com/me"
        params = {
            "fields": "id,name,email,picture",
            "access_token": token
        }

        async with httpx.AsyncClient() as client:
            res = await client.get(facebook_url, params=params)

        if res.status_code != 200:
            print("Facebook error response:", res.text)
            raise HTTPException(status_code=400, detail="Failed to fetch user info from Facebook")

        user_data = res.json()
        email = user_data.get("email")
        name = user_data.get("name")
        facebookId = user_data.get("id")
        picture = user_data.get("picture")

        if not email:
            raise HTTPException(status_code=400, detail="Email not found in Facebook response")

        user = db.query(AuthUser).filter(AuthUser.email == email).first()
        if not user:
            dummy_password = pwd_context.hash("FACEBOOK_AUTH_NO_PASSWORD")
            user = AuthUser(email=email, fullName=name, password=dummy_password, provider="facebook", facebookId=facebookId, picture=picture)
            db.add(user)
            db.commit()
            db.refresh(user)

        access_token = create_access_token(data={"sub": email, "user_id": str(user.id)})
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="Lax",
            max_age=3600
        )

        return {"access_token": access_token, "token_type": "bearer"}
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
