from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional

from models.authModel.authModel import AuthUser
from schemas.adminSchema.noticeSchema import NoticeCreate, NoticeUpdate, NoticeResponse
from models.adminModel.noticeModel import Notice
from config import get_db
from send_email import send_email
from utils.utils import decode_access_token

router = APIRouter(prefix="/notices", tags=["Notices"])

# 🟢 CREATE
@router.post("/", response_model=NoticeResponse)
def create_notice(
    payload: NoticeCreate,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    
    # Fetch all user emails from DB
    users = db.query(AuthUser.email).all()

    # Convert list of tuples [(email1,), (email2,), ...] → [email1, email2, ...]
    user_emails = [email for (email,) in users]

    # Merge with any recipients passed in payload
    recipients = list(set((payload.recipients or []) + user_emails)) or []

    # 1. Save to DB
    notice = Notice(
        title=payload.title,
        content=payload.content,
        expires_at=payload.expires_at if payload.expires_at else None,
        recipients=recipients,
        send_email=payload.send_email
    )
    db.add(notice)
    db.commit()
    db.refresh(notice)

    # 2. If email needs to be sent
    if payload.send_email:
        if not payload.recipients or len(payload.recipients) == 0:
            raise HTTPException(status_code=400, detail="Recipients required if sending email.")

        html_content = f"<h3>{payload.title}</h3><p>{payload.content}</p>"
        background_tasks.add_task(send_email, payload.title, html_content, payload.recipients)

    return notice


# 🔵 READ (ALL)
@router.get("/", response_model=List[NoticeResponse])
def get_notices(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500)
):
    notices = db.query(Notice).offset(skip).limit(limit).all()
    return notices


# 🔵 READ (BY ID)
@router.get("/{notice_id}", response_model=NoticeResponse)
def get_notice_by_id(notice_id: int, db: Session = Depends(get_db)):
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")
    return notice


# 🟠 UPDATE
@router.put("/{notice_id}", response_model=NoticeResponse)
def update_notice(
    notice_id: int,
    payload: NoticeUpdate,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")

    # Update fields
    notice.title = payload.title or notice.title
    notice.content = payload.content or notice.content
    notice.recipients = payload.recipients or notice.recipients
    notice.send_email = payload.send_email if payload.send_email is not None else notice.send_email

    db.commit()
    db.refresh(notice)

    # Optional: resend email if send_email=True in update
    if payload.send_email:
        if not notice.recipients or len(notice.recipients) == 0:
            raise HTTPException(status_code=400, detail="Recipients required if sending email.")
        html_content = f"<h3>{notice.title}</h3><p>{notice.content}</p>"
        background_tasks.add_task(send_email, notice.title, html_content, notice.recipients)

    return notice


# 🔴 DELETE
@router.delete("/{notice_id}")
def delete_notice(notice_id: int, db: Session = Depends(get_db)):
    notice = db.query(Notice).filter(Notice.id == notice_id).first()
    if not notice:
        raise HTTPException(status_code=404, detail="Notice not found")

    db.delete(notice)
    db.commit()
    return {"message": "Notice deleted successfully", "id": notice_id}


# 🔵 READ (BY USER EMAIL)
@router.get("/my-notices", response_model=List[NoticeResponse])
def get_my_notices(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        # 🟢 Extract JWT token from cookie
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Access token missing")

        # 🟢 Decode token and get user_id
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # 🟢 Fetch user's email
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if not user or not user.email:
            raise HTTPException(status_code=404, detail="User not found")

        user_email = user.email

        # 🟢 Fetch all notices where user is a recipient and notice not expired
        current_time = datetime.utcnow()
        notices = (
            db.query(Notice)
            .filter(
                Notice.recipients.contains([user_email]),
                (Notice.expires_at == None) | (Notice.expires_at > current_time)
            )
            .all()
        )

        if not notices:
            raise HTTPException(status_code=404, detail="No active notices found for this user")

        return notices

    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {str(e)}")
