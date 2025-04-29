from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class ChatConfig(Base):
    __tablename__ = 'chat_configs'

    id = Column(Integer, primary_key=True)
    title_value = Column(String)
    title_is_active = Column(Boolean)
    welcome_message_value = Column(String)
    welcome_message_is_active = Column(Boolean)
    suggestions_value = Column(String)
    suggestions_is_active = Column(Boolean)
    placeholder_value = Column(String)
    placeholder_is_active = Column(Boolean)
    lead_collection = Column(Boolean)

    # one-to-one relationship with BrandingConfig
    branding_id = Column(Integer, ForeignKey('branding_configs.id'))
    branding = relationship("BrandingConfig", back_populates="chat_config")

class BrandingConfig(Base):
    __tablename__ = 'branding_configs'

    id = Column(Integer, primary_key=True)
    send_button_color = Column(String)
    chat_icon = Column(String)  # could store URL or base64 string
    chat_icon_color = Column(String)

    # one-to-one relationship with ChatbotConfig
    chatbot_id = Column(Integer, ForeignKey('chatbot_configs.id'))
    chatbot = relationship("ChatbotConfig", back_populates="branding")

    user_message_bg = Column(String)

    chat_config = relationship("ChatConfig", uselist=False, back_populates="branding")

class ChatbotConfig(Base):
    __tablename__ = 'chatbot_configs'

    id = Column(Integer, primary_key=True)
    image = Column(String)
    dots_color = Column(String)
    message_bg = Column(String)
    live_message_bg = Column(String)

    branding = relationship("BrandingConfig", uselist=False, back_populates="chatbot")
