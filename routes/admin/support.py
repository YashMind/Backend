
from typing import List
from fastapi import Request,APIRouter, BackgroundTasks, HTTPException,Depends
from decorators.rbac_admin import check_permissions
from schemas.adminSchema.adminSchema import PostEmail
from send_email import send_email
from sqlalchemy.orm import Session
from config import get_db, settings
from models.supportTickets.models import SupportTicket, Status
from models.authModel.authModel import AuthUser
from bs4 import BeautifulSoup


router = APIRouter()

def send_emails_in_batches(subject: str, content: str, recipients: List[str]):
    batch_size = 50  # adjust based on your SMTP or provider limits
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i:i + batch_size]
        send_email(subject=subject, html_content=content, recipients=batch)



@router.post("/send-email")
@check_permissions(['support-communication'], allow_anonymous=True)
def send_post_to_users(
    request: Request, 
    payload: PostEmail, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db)
):
    try:
        if not payload.recipients or len(payload.recipients) == 0:
            raise HTTPException(status_code=400, detail="At least one recipient is required.")
        
        content = f"<h3>{payload.title or ''}</h3><p>{payload.description or ''}</p>"

        ticket_ids = []
        for recipient in payload.recipients:
            user = db.query(AuthUser).filter(AuthUser.email == recipient).first()
            soup = BeautifulSoup(payload.html_content or '', "html.parser")
            plain_text = soup.get_text(separator="\n", strip=True)

  
            
            combined_message = (
                f"{payload.description}\n\n"
                f"--- User Details Extracted ---\n"
                f"{plain_text}"
            )   
            print("saving support ticket in DB")
            db_ticket = SupportTicket(
                subject=payload.title,
                message=combined_message, 
                handled_by=None,
                status=Status.pending,
                user_id=user.id if user else None,  # link if found

                # user_phone=user.phone if user and user.phone else None
            )
            print("db--",db_ticket)
            db.add(db_ticket)
            db.commit()
            db.refresh(db_ticket)
            ticket_ids.append(db_ticket.id)


        # queue background task for email sending
        background_tasks.add_task(
            send_emails_in_batches,
            payload.title or '',
            content or '',
            payload.recipients
        )

        return {
            "message": "Emails are being sent in the background",
            "ticket_id": db_ticket.id
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Error occurred while queuing email task: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while sending emails.")
