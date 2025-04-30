from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base


from sqlalchemy.orm import Session

Base = declarative_base()

# Combined single table model
class ChatSettings(Base):
    __tablename__ = 'chat_settings'

    id = Column(Integer, primary_key=True)
    bot_id = Column(Integer, ForeignKey("chat_bots.id"))
    # Chat config fields
    title_value = Column(String)
    title_is_active = Column(Boolean)
    welcome_message_value = Column(String)
    welcome_message_is_active = Column(Boolean)
    suggestions_value = Column(String)
    suggestions_is_active = Column(Boolean)
    placeholder_value = Column(String)
    placeholder_is_active = Column(Boolean)
    lead_collection = Column(Boolean)
    
    # Branding config fields
    send_button_color = Column(String)
    chat_icon = Column(String)
    chat_icon_color = Column(String)
    user_message_bg = Column(String)
    
    # Chatbot config fields
    image = Column(String)
    dots_color = Column(String)
    message_bg = Column(String)
    live_message_bg = Column(String)

    bot = relationship("ChatBots", backref="settings")

