from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
Base = declarative_base()

class Settings(Base):
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    push_notification_admin_email = Column(String(255), nullable=False)
    toggle_push_notifications = Column(Boolean, default=False)  # Enable/disable push notifications
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class SettingsBase(BaseModel):
    push_notification_admin_email: EmailStr = Field(..., description="Admin email for push notifications")
    toggle_push_notifications: bool = Field(False, description="Enable or disable push notifications")

class SettingsCreate(SettingsBase):
    pass  # same as base for now

class SettingsUpdate(BaseModel):
    push_notification_admin_email: Optional[EmailStr] = Field(None, description="Admin email for push notifications")
    toggle_push_notifications: Optional[bool] = Field(None, description="Enable or disable push notifications")

class SettingsRead(SettingsBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
        
        
        
 
 
        