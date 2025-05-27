from sqlalchemy import Column, ForeignKey, Integer, String, Enum, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum as PyEnum
from config import Base

class Status(str, PyEnum):
    pending = "pending"
    invalid = "Invalid"
    resolved = "resolved"
    in_process = "in process"
    issue_bug = "issue/bug"

class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, index=True)
    user_id= Column(Integer, ForeignKey("users.id"))
    subject = Column(String(255))
    message = Column(String(1000))
    status = Column(Enum(Status), default=Status.pending)
    handled_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reverted_at = Column(DateTime, nullable=True)
    thread_link = Column(String(512), nullable=True)
    
    user = relationship("AuthUser", backref="support_tickets")