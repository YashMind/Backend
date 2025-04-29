
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship
from datetime import datetime
from config import Base


class DBInstructionPrompt(Base):
    __tablename__ = "instruction_prompts"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    bot_id = Column(Integer, ForeignKey("chat_bots.id"))
    type = Column(String(255), unique=True)
    prompt = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    bot = relationship("ChatBots")