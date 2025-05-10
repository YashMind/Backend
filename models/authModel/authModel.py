from sqlalchemy import Column, Integer, Text, String, Boolean, DateTime, func, JSON
from config import Base

class AuthUser(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    fullName = Column(String(100), nullable=True)
    email = Column(String(100), nullable=True)
    password = Column(String(255), nullable=False)
    isRestricted = Column(Boolean, default=False)
    isMFA = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    provider = Column(String(255), nullable=True)
    googleId = Column(String(255), nullable=True)
    facebookId = Column(String(255), nullable=True)
    picture = Column(String(255), nullable=True)
    role = Column(String(100), nullable=True)
    status = Column(String(100), nullable=True)
    plan = Column(String(100), nullable=True)
    tokenUsed = Column(Integer, nullable=True)
    last_active = Column(DateTime(timezone=True), nullable=True)
    role_permissions = Column(JSON, nullable=True)


