from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from config import Base

class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String(255), nullable=False)  # ✅ Length added
    role = Column(String(100), nullable=False)      # ✅ Length added
    action = Column(String(255), nullable=False)    # ✅ Length added
    log_activity = Column(String(500), nullable=False)  # ✅ Length added
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
