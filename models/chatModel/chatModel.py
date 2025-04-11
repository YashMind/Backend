from sqlalchemy import Column, Integer, String, ForeignKey, Text, Enum, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config import Base

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(255), default="New Chat")
    created_at = Column(TIMESTAMP, server_default=func.now())

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chat_sessions.id"))
    sender = Column(Enum("user", "bot", name="sender_enum"))
    message = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())