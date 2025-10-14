from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from decorators.public import public_route
from decorators.rbac_admin import check_permissions
from models.supportTickets.models import SupportTicket, Status
from schemas.supportTickets.schema import (
    EmailRequest,
    TicketCreate,
    TicketResponse,
    TicketStatusUpdate,
    TicketAssign,
)
from config import get_db, settings
from datetime import datetime
from typing import List, Optional
from utils.utils import decode_access_token
from email.utils import make_msgid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

router = APIRouter(tags=["tickets"])


def extract_message_id(thread_link: Optional[str]) -> Optional[str]:
    """
    Extract Message-ID from thread_link.
    For SMTP, we'll store the Message-ID as the thread_link.
    """
    if not thread_link:
        return None
    return thread_link


def send_email(
    subject: str,
    html_content: str,
    recipients: List[str],
    in_reply_to: Optional[str] = None,
    references: Optional[str] = None,
) -> str:
    """
    Send email and return the Message-ID.
    If in_reply_to and references are provided, will thread the emails.
    """
    msg = MIMEMultipart()
    msg["From"] = settings.EMAIL_ADDRESS
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject

    # Generate a new Message-ID for this email
    message_id = make_msgid()
    msg["Message-ID"] = message_id

    # Add threading headers if this is a reply
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references if references else in_reply_to

    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
            server.send_message(msg)

        print(f"Email sent to {recipients}")
        return message_id[1:-1]  # Remove < and > from Message-ID

    except Exception as e:
        print(f"Failed to send email to {recipients}: {e}")
        raise Exception(f"Failed to send email: {e}")


@router.post("/", response_model=TicketResponse)
@public_route()
def create_ticket(
    request: Request, ticket: TicketCreate, db: Session = Depends(get_db)
):
    print("-----------------------------")
    token = request.cookies.get("access_token")
    print(f"Token: {token}") 
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))
    print(f"Extracted user_id: {user_id}") 
    print("_____________________________",user_id)
    db_ticket = SupportTicket(**ticket.dict(), user_id=user_id)
    db.add(db_ticket)
    db.commit()
    db.refresh(db_ticket)
    print(f"Created ticket ID: {db_ticket.id}")
    print(f"Ticket user_id in DB: {db_ticket.user_id}")
    
    return db_ticket


@router.get("/", response_model=list[TicketResponse])
@check_permissions(["support-communication"])
def get_all_tickets(
    request: Request, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    # print(" api hit")
    return (
        db.query(SupportTicket)
        .order_by(SupportTicket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/user", response_model=List[TicketResponse])
@public_route()
def get_user_tickets(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.user_id == user_id)
        .order_by(SupportTicket.created_at.desc())
        .all()
    )
    return tickets


@router.get("/{ticket_id}", response_model=TicketResponse)
@public_route()
def get_ticket(request: Request, ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}/status", response_model=TicketResponse)
@check_permissions(["support-communication"])
def update_status(
    request: Request,
    ticket_id: int,
    status: TicketStatusUpdate,
    db: Session = Depends(get_db),
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.status = status.status
    ticket.reverted_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)

    # Send status notification
    if ticket.user and ticket.user.email:
        try:
            html_content = f"""
            <html>
                <body>
                    <h2>Ticket Status Update: {ticket.subject}</h2>
                    <p>Your ticket status has been updated to: <strong>{ticket.status}</strong></p>
                    <p>Original message: {ticket.message}</p>
                    <p>Handled by: {ticket.handled_by or 'Not assigned yet'}</p>
                    <p>Thank you for your patience.</p>
                </body>
            </html>
            """

            # Get threading info if exists
            in_reply_to = extract_message_id(ticket.thread_link)
            references = in_reply_to

            # Send email
            message_id = send_email(
                subject=f"Status Update: {ticket.subject}",
                html_content=html_content,
                recipients=[ticket.user.email],
                in_reply_to=in_reply_to,
                references=references,
            )

            # Update thread link if this was the first email
            if not ticket.thread_link:
                ticket.thread_link = message_id
                db.commit()
                db.refresh(ticket)

        except Exception as e:
            print(f"Failed to send status notification: {e}")

    return ticket


@router.patch("/{ticket_id}/assign", response_model=TicketResponse)
@check_permissions(["support-communication"])
def assign_ticket(
    request: Request,
    ticket_id: int,
    assign: TicketAssign,
    db: Session = Depends(get_db),
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.handled_by = assign.handled_by
    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/send-reply")
def send_ticket_reply(
    ticket_id: int, email_request: EmailRequest, db: Session = Depends(get_db)
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Customize the email content
    html_content = f"""
    <html>
        <body>
            <h2>Re: {ticket.subject}</h2>
            <p><strong>Your original message:</strong></p>
            <p>{ticket.message}</p>
            <hr>
            <p><strong>Our response:</strong></p>
            <p>{email_request.message}</p>
            <p>Ticket status: {ticket.status}</p>
            <p>Thank you for contacting support.</p>
        </body>
    </html>
    """
    try:
        # Get threading info if exists
        in_reply_to = extract_message_id(ticket.thread_link)
        references = in_reply_to

        # Send email
        message_id = send_email(
            subject=f"Re: {ticket.subject}",
            html_content=html_content,
            recipients=email_request.recipients,
            in_reply_to=in_reply_to,
            references=references,
        )

        # Update thread link if this was the first email
        if not ticket.thread_link:
            ticket.thread_link = message_id
            db.commit()
            db.refresh(ticket)

        return {"message": "Reply sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to send email: {e}")


@router.post("/{ticket_id}/status-notification")
@check_permissions(["support-communication"])
def send_status_notification(
    request: Request, ticket_id: int, db: Session = Depends(get_db)
):
    ticket = db.query(SupportTicket).filter(SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if not ticket.user.email:
        raise HTTPException(
            status_code=400, detail="Ticket has no associated user email"
        )

    html_content = f"""
    <html>
        <body>
            <h2>Ticket Status Update: {ticket.subject}</h2>
            <p>Your ticket status has been updated to: <strong>{ticket.status}</strong></p>
            <p>Original message: {ticket.message}</p>
            <p>Handled by: {ticket.handled_by or 'Not assigned yet'}</p>
            <p>Thank you for your patience.</p>
        </body>
    </html>
    """
    try:
        # Get threading info if exists
        in_reply_to = extract_message_id(ticket.thread_link)
        references = in_reply_to

        # Send email
        message_id = send_email(
            subject=f"Status Update: {ticket.subject}",
            html_content=html_content,
            recipients=[ticket.user.email],
            in_reply_to=in_reply_to,
            references=references,
        )

        # Update thread link if this was the first email
        if not ticket.thread_link:
            ticket.thread_link = message_id
            db.commit()
            db.refresh(ticket)

        return {"message": "Status notification sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to send email: {e}")


# Request model for sending emails
class EmailSendRequest(BaseModel):
    subject: str
    html_content: str
    recipients: List[str]
    in_reply_to: str = None  # For threading
    references: str = None  # For threading


@router.post("/send-email")
def send_email_api(email_request: EmailSendRequest, db: Session = Depends(get_db)):
    """
    Send an email with HTML content

    Parameters:
    - subject: Email subject
    - html_content: HTML formatted email content
    - recipients: List of recipient email addresses
    - in_reply_to: Optional message ID for threading
    - references: Optional references for threading
    """
    try:
        message_id = send_email(
            subject=email_request.subject,
            html_content=email_request.html_content,
            recipients=email_request.recipients,
            in_reply_to=email_request.in_reply_to,
            references=email_request.references,
        )
        print("+==")
        return {"message": "Email sent successfully", "message_id": message_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to send email: {str(e)}")
