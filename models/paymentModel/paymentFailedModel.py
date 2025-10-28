from sqlalchemy import Column, Integer, Boolean, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional
from datetime import datetime

Base = declarative_base()


# -----------------------------
# SQLAlchemy Model
# -----------------------------
class Settings(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    push_notification_admin_emails = Column(JSON, default=[])  # store array of emails
    toggle_push_notifications = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

# -----------------------------
# Pydantic Schemas
# -----------------------------
class SettingsBase(BaseModel):
    push_notification_admin_emails: List[EmailStr] = Field(default_factory=list)
    toggle_push_notifications: bool = False

    @validator("push_notification_admin_emails", pre=True)
    def remove_empty_emails(cls, v):
        if not v:
            return []
        return [email.strip() for email in v if email and email.strip()]


class SettingsCreate(SettingsBase):
    pass


class SettingsUpdate(BaseModel):
    push_notification_admin_emails: Optional[List[EmailStr]] = None
    toggle_push_notifications: Optional[bool] = None


class SettingsRead(SettingsBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True