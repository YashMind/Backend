# schemas/announcementSchema.py

from typing import Optional
from pydantic import BaseModel

class AnnouncementCreate(BaseModel):
    title: str
    content: str

class AnnouncementUpdate(BaseModel):
    title: Optional[str]  = None
    content: Optional[str] = None
