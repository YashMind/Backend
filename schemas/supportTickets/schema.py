from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import List, Optional
from enum import Enum

from schemas.authSchema.authSchema import User

class Status(str, Enum):
    pending = "pending"
    invalid = "Invalid"
    resolved = "resolved"
    in_process = "in process"
    issue_bug = "issue/bug"

class TicketCreate(BaseModel):
    subject: str
    message: str

class TicketResponse(BaseModel):
    id: int
    subject: str
    message: str
    status: Status
    user: User  | None
    handled_by: Optional[str]
    created_at: datetime
    reverted_at: Optional[datetime]
    thread_link: Optional[str]

    class Config:
        orm_mode = True

class TicketStatusUpdate(BaseModel):
    status: Status

class TicketAssign(BaseModel):
    handled_by: str
    
    
class EmailRequest(BaseModel):
    subject: str
    message: str
    recipients: List[EmailStr]