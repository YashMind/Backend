from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship
from datetime import datetime
from config import Base


class DBInstructionPrompt(Base):
    __tablename__ = "instruction_prompts"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer)
    bot_id = Column(Integer, ForeignKey("chat_bots.id"))
    type = Column(String(255))
    prompt = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    bot = relationship("ChatBots")

    __table_args__ = (UniqueConstraint('bot_id', 'type', name='_bot_type_uc'),)

