# models/installation.py
from sqlalchemy import Column, String, DateTime, Integer
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
