from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, Enum, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config import Base

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String(255), default="New Chat")
    created_at = Column(TIMESTAMP, server_default=func.now())
    messages = relationship("ChatMessage", back_populates="chat_session")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chat_sessions.id"))
    sender = Column(Enum("user", "bot", name="sender_enum"))
    message = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
    chat_session = relationship("ChatSession", back_populates="messages")

class ChatBots(Base):
    __tablename__ = "chat_bots"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    chatbot_name = Column(String(255), nullable=False)
    train_from = Column(String(255), nullable=True)
    target_link = Column(String(255), nullable=True)
    document_link = Column(String(255), nullable=True)
    public = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())

