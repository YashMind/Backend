from sqlalchemy import Column, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel

from sqlalchemy import Column, Integer, String
from config import Base  # Use your actual Base import

class ToolsUsed(Base):
    __tablename__ = 'tools_used'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)


class ToolStatusUpdate(BaseModel):
    status: str