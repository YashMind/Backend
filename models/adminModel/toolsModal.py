from sqlalchemy import Boolean, Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel

from sqlalchemy import Column, Integer, String
from config import Base  # Use your actual Base import


class ToolsUsed(Base):
    __tablename__ = "tools_used"

    id = Column(Integer, primary_key=True, index=True)
    tool = Column(String(255), nullable=False)
    model = Column(String(255), nullable=False)
    status = Column(Boolean, nullable=False, default=False)


class ToolStatusUpdate(BaseModel):
    status: bool
