from sqlalchemy import Column, Integer, String, DateTime,Float
from sqlalchemy.sql import func
from config import Base

class APICallLog(Base):
    __tablename__ = "api_call_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)           # ID of the user
    description = Column(String(500), nullable=True)    # Optional description
    duration = Column(Float, nullable=True)  # duration in seconds
    called_at = Column(DateTime(timezone=True), server_default=func.now())  # API call timestamp
