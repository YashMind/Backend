from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response, Form
from passlib.context import CryptContext
from utils.utils import create_access_token, decode_access_token, create_reset_token, send_reset_email, decode_reset_access_token, get_current_user
from jose import JWTError, jwt
from uuid import uuid4
import json
from models.authModel import AuthUser
from schemas.authSchems import User, PasswordResetRequest, PasswordReset
from sqlalchemy.orm import Session
from config import get_db

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.post("/signup")
async def signup(user: User, db: Session = Depends(get_db)):
    try:
        fullName = user.fullName
        email = user.email
        password = user.password
        if not fullName or not email or not password:
            raise HTTPException(status_code=400, detail="email and password are required")
        hashed_password = pwd_context.hash(user.password)
        existing_user = db.query(AuthUser).filter(AuthUser.email == email).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="email already registered")

        new_user = AuthUser(
            fullName=fullName,
            email=email,
            password=hashed_password
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {"message": "User created successfully"}
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.post("/signin")
async def signin(user: User, response: Response, db: Session = Depends(get_db)):
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
        response.set_cookie(key="access_token", value=access_token, httponly=True)

        return {"access_token": access_token, "token_type": "bearer"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/me")
async def getme(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        payload = decode_access_token(token)
        email = payload.get("sub")
        user = db.query(AuthUser).filter(AuthUser.email == email).first()
        if not user:
            raise HTTPException(status_code=400, detail="User not found")

        return {"user": user, "status": 200}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

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
        raise HTTPException(status_code=500, detail="An unexpected error occurred") from e

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
        raise HTTPException(status_code=500, detail="Token decoding error") from e

# current_user: dict = Depends(get_current_user)
@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    try:
        response.delete_cookie(key="access_token")
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during logout") from e