from fastapi import APIRouter, Depends, HTTPException,Query,Request
from sqlalchemy.orm import Session
from models.activityLogModel.activityLogModel import ActivityLog
from config import get_db  
from schemas.activityLog.activitylog import ActivityLogSchema
from typing import List,Optional
from datetime import datetime, timedelta

router = APIRouter()


@router.get("/activity-logs", response_model=list[ActivityLogSchema])
def get_activity_logs(request: Request, db: Session = Depends(get_db)):
    raw_start = request.query_params.get("start_date")

    query = db.query(ActivityLog)

    if raw_start is not None:  # Means the user provided the param (even if it's an empty string)
        if raw_start.strip():  # Check if it's not empty
            try:
                start_date = datetime.strptime(raw_start, "%Y-%m-%d")
                end_date = start_date + timedelta(days=1)
                query = query.filter(ActivityLog.created_at >= start_date, ActivityLog.created_at < end_date)
            except ValueError:
                return []  # Invalid date = return empty list
        else:
            return []  # If param is explicitly "" (empty string), return empty list
    else:
        # If no 'start_date' param provided at all, return all logs
        pass

    logs = query.order_by(ActivityLog.created_at.desc()).all()
    return logs

# @router.get("/activity-logs", response_model=List[ActivityLogSchema])
# def get_activity_logs(
#     start_date: Optional[datetime] = Query(None),
#     end_date: Optional[datetime] = Query(None),
#     db: Session = Depends(get_db)
# ):
#     query = db.query(ActivityLog)

#     if start_date:
#         query = query.filter(ActivityLog.created_at >= start_date)
#     if end_date:
#         query = query.filter(ActivityLog.created_at <= end_date)

#     logs = query.order_by(ActivityLog.created_at.desc()).all()
#     return logs

# @router.get("/activity-logs", response_model=list[ActivityLogSchema])
# def get_all_activity_logs(db: Session = Depends(get_db)):
#     try:
#         logs = db.query(ActivityLog).order_by(ActivityLog.created_at.desc()).all()
#         return logs
#     except Exception as e:
#         raise HTTPException(status_code=500, detail="Could not fetch logs")
# @router.get("/get-activity-logs", response_model=List[ActivityLogSchema])
# def get_activity_logs(user_id: Optional[int] = None, action: Optional[str] = None, db: Session = Depends(get_db)):
#     query = db.query(ActivityLog)
#     if user_id:
#         query = query.filter(ActivityLog.user_id == user_id)
#     if action:
#         query = query.filter(ActivityLog.action == action)
#     return query.order_by(ActivityLog.created_at.desc()).all()
