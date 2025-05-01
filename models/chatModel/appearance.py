from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base


from sqlalchemy.orm import Session
from config import Base


# Combined single table model
class ChatSettings(Base):
    __tablename__ = 'chat_settings'

    id = Column(Integer, primary_key=True)
    bot_id = Column(Integer)
    # Chat config fields
    title_value = Column(String(25))
    title_is_active = Column(Boolean)
    welcome_message_value = Column(String(70))
    welcome_message_is_active = Column(Boolean)
    suggestions_value = Column(String(500))
    suggestions_is_active = Column(Boolean)
    placeholder_value = Column(String(60))
    placeholder_is_active = Column(Boolean)
    lead_collection = Column(Boolean)
    
    # Branding config fields
    chat_window_bg = Column(String(10))
    send_button_color = Column(String(10))
    chat_icon = Column(String(100))
    chat_icon_color = Column(String(10))
    user_message_bg = Column(String(10))
    
    # Chatbot config fields
    image = Column(String(100))
    dots_color = Column(String(10))
    message_bg = Column(String(10))
    live_message_bg = Column(String(10))

    # bot = relationship("ChatBots", backref="settings")
    class Config:
        orm_mode =True

