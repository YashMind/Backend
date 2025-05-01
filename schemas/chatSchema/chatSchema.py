
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Chat Message Schema
class ChatMessageBase(BaseModel):
    message: str


class ChatMessageCreate(ChatMessageBase):
    sender: str  # "user" or "bot"


class ChatMessageRead(ChatMessageBase):
    id: Optional[int] = None
    chat_id: Optional[int] = None
    bot_id: Optional[int] = None
    user_id: Optional[int] = None
    sender: Optional[str] = None
    created_at: Optional[datetime] = None
    message: Optional[str] = None

    class Config:
        orm_mode = True

# Chat Session Schema
class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Chat"


class ChatSessionRead(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    bot_id: int
    title: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        orm_mode = True


class ChatSessionWithMessages(ChatSessionRead):
    messages: List[ChatMessageRead]

class CreateBot(BaseModel):
    id: Optional[int] = None
    chatbot_name: Optional[str] = None
    user_id: Optional[int] = None
    train_from: Optional[str] = None
    target_link: Optional[str] = None
    document_link: Optional[str] = None
    public: Optional[bool] = False
    text_content: Optional[str] = None
    creativity: Optional[int] = None
    token: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class DeleteChatsRequest(BaseModel):
    chat_ids: List[int]

class QuestionAnswer(BaseModel):
    id: Optional[int] = None
    user_id: Optional[int] = None
    bot_id: Optional[int] = None
    question: str
    answer: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class CreateBotFaqs(BaseModel):
    bot_id: int
    questions: Optional[List[QuestionAnswer]] = None

    class Config:
        orm_mode = True

class FaqResponse(BaseModel):
    id: int
    user_id: int
    bot_id: int
    question: str
    answer: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        orm_mode = True


class CreateBotDocLinks(BaseModel):
    id: Optional[int] = None
    bot_id: Optional[int] = None
    chatbot_name: Optional[str] = None
    user_id: Optional[int] = None
    train_from: Optional[str] = None
    target_link: Optional[str] = None
    document_link: Optional[str] = None
    public: Optional[bool] = False
    text_content: Optional[str] = None
    status: Optional[str] = None
    chars: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class DeleteDocLinksRequest(BaseModel):
    doc_ids: List[int]

