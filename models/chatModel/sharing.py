from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Text, Enum, TIMESTAMP
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config import Base

class ChatBotSharing(Base):
    __tablename__ = "chatbot_sharing"
    
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("chat_bots.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    shared_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    shared_email = Column(String(255), nullable=True)
    invite_token = Column(String(255), nullable=True, unique=True)
    status = Column(Enum("pending", "active", "revoked", name="sharing_status_enum"), default="pending")
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())
    
    # Define relationships if needed
    # bot = relationship("ChatBots", back_populates="shared_with")
    # owner = relationship("AuthUser", foreign_keys=[owner_id])
    # shared_user = relationship("AuthUser", foreign_keys=[shared_user_id])
