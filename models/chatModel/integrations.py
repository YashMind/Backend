# models/installation.py
from sqlalchemy import Boolean, Column, String, DateTime, Integer, ForeignKey, Text
from config import Base
from datetime import datetime


class SlackInstallation(Base):
    __tablename__ = "slack_installations"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String(100), nullable=False)
    team_id = Column(String(100), nullable=False, unique=True)
    team_name = Column(String(255), nullable=False)
    bot_user_id = Column(String(100), nullable=False)
    authed_user_id = Column(String(100), nullable=False)
    access_token = Column(String(255), nullable=False)
    installed_at = Column(DateTime, default=datetime.utcnow)

class WhatsAppUser(Base):
    __tablename__ = "whatsapp_users"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(String(100), nullable=False)
    whatsapp_number = Column(String(20), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    
    # WhatsApp Business API Fields (replacing Twilio fields)
    access_token = Column(Text, nullable=False)  # Permanent access token
    phone_number_id = Column(String(50), nullable=False)  # WhatsApp business phone ID
    business_account_id = Column(String(50), nullable=False)  # WhatsApp business account ID
    webhook_secret= Column(String(255), nullable=True)
    waba_id = Column(String(50))  # WhatsApp Business Account ID (optional)
    display_name = Column(String(100))  # Business display name
    
    # Verification/Status Fields
    verification_status = Column(String(20), default="pending")  # pending/verified/failed
    name_status = Column(String(20))  # APPROVED/PENDING/REJECTED for business name
    quality_rating = Column(String(20))  # GREEN/YELLOW/RED for account quality
    
    # Usage Tracking
    message_count = Column(Integer, default=0)
    last_message_at = Column(DateTime)
    tier = Column(String(20))  # Business tier if applicable
    
    # Status Flags
    is_active = Column(Boolean, default=True)
    is_official_business_account = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    opt_in_date = Column(DateTime)  # When user opted in
    name_update_date = Column(DateTime)  # Last business name update

class ZapierIntegration(Base):
    __tablename__ = "zapier_integrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    bot_id = Column(Integer, ForeignKey("chat_bots.id"))
    api_token = Column(String(255), index=True)
    email = Column(String(255), nullable=True)
    subscribed = Column(Boolean, default=False)
    webhook_url = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
