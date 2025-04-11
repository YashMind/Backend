
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
