from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime
from config import Base

class Announcement(Base):
    __tablename__ = "announcement"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)  # ✅ Length added here
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
