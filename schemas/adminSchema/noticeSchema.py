from datetime import datetime
from typing import Optional,List
from pydantic import BaseModel,EmailStr

class NoticeCreate(BaseModel):
    title: str
    content: str
    recipients: Optional[List[EmailStr]] = None
    send_email: bool
    expires_at: Optional[datetime] = None  # 👈 optional expiry
