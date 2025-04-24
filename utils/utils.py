from fastapi import HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional
from sqlalchemy.orm import Session
from config import get_db
from models.authModel.authModel import AuthUser
from email.mime.text import MIMEText
import smtplib
import httpx

SECRET_KEY = "ADMIN@1234QWER"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 20160  # 2 weeks
RESET_PASSWORD_TOKEN_EXPIRE_MINUTES = 15

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    
def decode_access_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

async def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No access token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        # orm
        user = db.query(AuthUser).filter(AuthUser.id==user_id).first()
        if user is None:
            raise credentials_exception
        # user['id'] = str(user.id)  
        return user
    except JWTError:
        raise credentials_exception
    
def create_reset_token(data: dict, expires_delta: Optional[timedelta] = None):
    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=RESET_PASSWORD_TOKEN_EXPIRE_MINUTES))
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except JWTError as jwt_exc:
        raise HTTPException(status_code=500, detail="Token creation error") from jwt_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred while creating the token") from e
    
def decode_reset_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

def send_reset_email(email: str, token: str):
    try:
        reset_link = f"http://localhost:3000/reset-password?token={token}"
        message = MIMEText(f"Click the link to reset your password: {reset_link}")
        message["Subject"] = "Password Reset"
        message["From"] = "no-reply@yourdomain.com"
        message["To"] = email

        # Send email (ensure you configure your SMTP server details)
        with smtplib.SMTP("smtp.yourdomain.com", 587) as server:
            server.starttls()
            server.login("your-email@yourdomain.com", "your-email-password")
            server.sendmail("no-reply@yourdomain.com", email, message.as_string())
    
    except smtplib.SMTPException as smtp_exc:
        raise HTTPException(status_code=500, detail="Failed to send reset email") from smtp_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="An unexpected error occurred while sending the email") from e

async def get_country_from_ip(ip: str):
    try:
        url = f"https://ipinfo.io/{ip}/json"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            print("response country ", response)
            if response.status_code == 200:
                data = response.json()
                print("data ", data)
                return data.get("country", "Unknown")
            return "Unknown"
    except Exception as e:
        print("IP API error", e)
        return "Unknown"

    
