from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.adminModel.announcementModel import Announcement
from schemas.adminSchema.announcementSchema import AnnouncementCreate, AnnouncementUpdate
from config import get_db

router = APIRouter()

# CREATE Announcement
@router.post("/announcements")
def create_announcement(payload: AnnouncementCreate, db: Session = Depends(get_db)):
    try:
        announcement = Announcement(title=payload.title, content=payload.content)
        db.add(announcement)
        db.commit()
        db.refresh(announcement)
        return {"message": "Announcement created successfully", "data": announcement}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creating announcement: {str(e)}")


# GET All Announcements (List)
@router.get("/announcements")
def fetch_announcements(db: Session = Depends(get_db)):
    try:
        announcements = db.query(Announcement).all()
        return {"message": "Announcements fetched successfully", "data": announcements}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching announcements: {str(e)}")


# GET Single Announcement by ID
@router.get("/announcements/{announcement_id}")
def fetch_single_announcement(announcement_id: int, db: Session = Depends(get_db)):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")
        return {"message": "Announcement fetched successfully", "data": announcement}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching announcement: {str(e)}")


# UPDATE Announcement by ID
@router.put("/announcements/{announcement_id}")
def update_announcement(announcement_id: int, payload: AnnouncementUpdate, db: Session = Depends(get_db)):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")

        announcement.title = payload.title or announcement.title
        announcement.content = payload.content or announcement.content
        db.commit()
        db.refresh(announcement)
        return {"message": "Announcement updated successfully", "data": announcement}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating announcement: {str(e)}")


# DELETE Announcement by ID
@router.delete("/announcements/{announcement_id}")
def delete_announcement(announcement_id: int, db: Session = Depends(get_db)):
    try:
        announcement = db.query(Announcement).filter(Announcement.id == announcement_id).first()
        if not announcement:
            raise HTTPException(status_code=404, detail="Announcement not found")

        db.delete(announcement)
        db.commit()
        return {"message": "Announcement deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error deleting announcement: {str(e)}")
