# models/installation.py
from sqlalchemy import Boolean, Column, String, DateTime, Integer, ForeignKey
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
    twilio_account_sid = Column(String(50))  # Store which Twilio account this uses
    verification_status = Column(String(20), default="pending")  # pending/verified/failed
    last_verified_at = Column(DateTime)
    message_count = Column(Integer, default=0)  # Track usage
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

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
