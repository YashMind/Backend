
from typing import List
from fastapi import APIRouter, BackgroundTasks, HTTPException
from decorators.rbac_admin import check_permissions
from schemas.adminSchema.adminSchema import PostEmail
from send_email import send_email

router = APIRouter()

def send_emails_in_batches(subject: str, content: str, recipients: List[str]):
    batch_size = 50  # adjust based on your SMTP or provider limits
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i:i + batch_size]
        send_email(subject=subject, html_content=content, recipients=batch)

@router.post("/send-emails")
@check_permissions(['support-communication'])
def send_post_to_users(payload: PostEmail, background_tasks: BackgroundTasks):
    try:
        if not payload.recipients or len(payload.recipients) == 0:
            raise HTTPException(status_code=400, detail="At least one recipient is required.")
        
        content = f"<h3>{payload.title}</h3><p>{payload.description}</p>"
        background_tasks.add_task(send_emails_in_batches, payload.title, content, payload.recipients)
        return {"message": "Emails are being sent in the background"}
    
    except HTTPException as e:
        # re-raise specific validation errors
        raise e

    except Exception as e:
        print(f"Error occurred while queuing email task: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while sending emails.")