from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.orm import Session
from models.activityLogModel.activityLogModel import ActivityLog
from config import get_db
from schemas.activityLog.activitylog import ActivityLogSchema, PaginatedActivityLogs
from typing import List, Optional
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/activity-logs", response_model=PaginatedActivityLogs)
def get_activity_logs(
    request: Request,
    db: Session = Depends(get_db),
    start_date: Optional[str] = Query(None),
    limit: int = Query(5, ge=1),
    offset: int = Query(0, ge=0)
):
    query = db.query(ActivityLog)

    if start_date is not None:
        if start_date.strip():
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                end_dt = start_dt + timedelta(days=1)
                query = query.filter(ActivityLog.created_at >= start_dt, ActivityLog.created_at < end_dt)
            except ValueError:
                return []
        else:
            pass  # Treat empty string as "get all"

    total = query.count()
    logs = query.order_by(ActivityLog.created_at.asc()).offset(offset).limit(limit).all()
    return {"logs": logs, "total": total}
