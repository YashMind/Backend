import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, TIMESTAMP, Index
from config import Base


class ChatbotTokenUsage(Base):
    __tablename__ = 'chatbot_tokens'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    chatbot_id = Column(String(36), nullable=False)
    session_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False)
    
    # Input tokens
    user_message = Column(Text, nullable=False)
    user_message_tokens = Column(Integer, nullable=False)
    
    # Processing details
    used_faq = Column(Boolean, default=False)
    used_vector_db = Column(Boolean, default=False)
    vector_db_context_tokens = Column(Integer, default=0)
    
    # OpenAI interaction
    openai_prompt_tokens = Column(Integer, default=0)
    openai_completion_tokens = Column(Integer, default=0)
    openai_total_tokens = Column(Integer, default=0)
    
    # Response details
    bot_response = Column(Text)
    bot_response_tokens = Column(Integer, nullable=False)
    
    # Timestamps
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    