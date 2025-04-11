from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
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
