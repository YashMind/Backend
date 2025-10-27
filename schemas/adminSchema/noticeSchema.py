from datetime import datetime
from pydantic import BaseModel, EmailStr
from typing import List, Optional

class NoticeBase(BaseModel):
    title: str
    content: str
    recipients: Optional[List[EmailStr]] = []
    expires_at: Optional[datetime]  # ✅ Change here
    send_email: bool = False

class NoticeCreate(NoticeBase):
    pass

class NoticeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    recipients: Optional[List[EmailStr]] = None
    send_email: Optional[bool] = None
    expires_at: Optional[datetime] = None 

class NoticeResponse(NoticeBase):
    id: int

    class Config:
        orm_mode = True
