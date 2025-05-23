from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime

class ChatbotSharingBase(BaseModel):
    bot_id: int
    
class DirectSharingRequest(ChatbotSharingBase):
    shared_user_id: int

class EmailInviteRequest(ChatbotSharingBase):
    shared_email: EmailStr

class BulkEmailInviteRequest(ChatbotSharingBase):
    user_emails: List[str]

class AcceptInviteRequest(BaseModel):
    token: str

class SharingResponse(BaseModel):
    id: int
    bot_id: int
    owner_id: int
    shared_user_id: Optional[int] = None
    shared_email: Optional[str] = None
    invite_token: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True

class InviteResponse(BaseModel):
    message: str
    invites: List[SharingResponse]

class AcceptInviteResponse(BaseModel):
    message: str
    sharing: SharingResponse
