from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import timedelta, datetime
class User(BaseModel):
    fullName: Optional[str]
    email: EmailStr
    password: str
    isRestricted: Optional[bool] = False

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    token: str
    new_password: str