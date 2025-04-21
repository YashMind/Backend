
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Chat Message Schema
class ChatMessageBase(BaseModel):
    message: str


class ChatMessageCreate(ChatMessageBase):
    sender: str  # "user" or "bot"


class ChatMessageRead(ChatMessageBase):
    id: int
    sender: str
    created_at: datetime
    message: List

    class Config:
        orm_mode = True

# Chat Session Schema
class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Chat"


class ChatSessionRead(BaseModel):
    id: int
    title: str
    created_at: datetime

    class Config:
        orm_mode = True


class ChatSessionWithMessages(ChatSessionRead):
    messages: List[ChatMessageRead]

class CreateBot(BaseModel):
    id: int
    chatbot_name: Optional[str] = None
    user_id: Optional[int] = None
    train_from: Optional[str] = None
    target_link: Optional[str] = None
    document_link: Optional[str] = None
    public: Optional[bool] = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

