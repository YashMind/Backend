from fastapi import APIRouter, BackgroundTasks, HTTPException,Depends
from schemas.adminSchema.noticeSchema import NoticeCreate
from models.adminModel.noticeModel import Notice
from sqlalchemy.orm import Session
from config import get_db
from send_email import send_email

router = APIRouter()

@router.post("/notices")
def create_notice(payload: NoticeCreate, db: Session = Depends(get_db), background_tasks: BackgroundTasks = None):
    # 1. Save to DB
    notice = Notice(
        title=payload.title,
        content=payload.content,
        recipients=payload.recipients,
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

    return {"message": "Notice created successfully", "id": notice.id}
