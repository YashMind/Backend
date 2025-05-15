from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.adminModel.announcementModel import Announcement
from schemas.adminSchema.announcementSchema import AnnouncementCreate
from config import get_db

router = APIRouter()

@router.post("/announcements")
def create_announcement(payload: AnnouncementCreate, db: Session = Depends(get_db)):
    announcement = Announcement(title=payload.title, content=payload.content)
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return {"message": "Announcement created", "data": announcement}
