from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import timedelta, datetime
class User(BaseModel):
    id: Optional[int] = None
    fullName: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    isRestricted: Optional[bool] = False
    role: Optional[str] = None
    status: Optional[str] = None
    plan: Optional[str] = None
    tokenUsed: Optional[int] = None

class SignInUser(BaseModel):
    email: EmailStr
    password: str
    role: Optional[str] = None

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    token: str
    new_password: str

class UserUpdate(BaseModel):
    fullName: Optional[str] = None
    password: Optional[str] = None
    isRestricted: Optional[bool] = False