from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.activityLogModel.activityLogModel import ActivityLog
from config import get_db  # or 'from config import get_db' based on your setup
from schemas.activityLog.activitylog import ActivityLogSchema

router = APIRouter()

@router.get("/activity-logs", response_model=list[ActivityLogSchema])
def get_all_activity_logs(db: Session = Depends(get_db)):
    try:
        logs = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).all()
        return logs
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not fetch logs")
# @router.get("/get-activity-logs", response_model=List[ActivityLogSchema])
# def get_activity_logs(user_id: Optional[int] = None, action: Optional[str] = None, db: Session = Depends(get_db)):
#     query = db.query(ActivityLog)
#     if user_id:
#         query = query.filter(ActivityLog.user_id == user_id)
#     if action:
#         query = query.filter(ActivityLog.action == action)
#     return query.order_by(ActivityLog.created_at.desc()).all()
