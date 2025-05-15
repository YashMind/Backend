# schemas/announcementSchema.py
from pydantic import BaseModel

class AnnouncementCreate(BaseModel):
    title: str
    content: str
