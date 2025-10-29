from sqlalchemy.orm import Session
from models.activityLogModel.activityLogModel import ActivityLog
from models.authModel.authModel import AuthUser
from models.subscriptions.transactionModel import Transaction
from models.supportTickets.models import SupportTicket
from send_email import send_email
from fastapi import APIRouter, Depends, HTTPException, Request,Query
from config import get_db
from datetime import datetime
import json
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status
from config import get_db
from pydantic import BaseModel, EmailStr
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from models.paymentModel.paymentFailedModel import Settings, SettingsCreate, SettingsUpdate, SettingsRead
from config import get_db
def handle_failed_payment(transaction_id: int, raw_data, db: Session, order_id: str=None):
    print(
        f"[DEBUG] Starting failed payment handler for transaction_id={transaction_id}"
    )
    

    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    print(f"[DEBUG] Fetched transaction using id: {transaction}")

    if not transaction:
        transaction = (
            db.query(Transaction).filter(Transaction.order_id == order_id).first()
        )
        print(f"[DEBUG] Fetched transaction using order_id: {transaction}")

    if not transaction:
        print("[ERROR] Transaction not found!")
        return

    user = db.query(AuthUser).filter(AuthUser.id == transaction.user_id).first()
    print(f"[DEBUG] Fetched user: {user}")

    if not user:
        print("[ERROR] User not found!")
        return

    subject = f"{transaction.order_id}: payment of user failed with transaction id {transaction.provider_transaction_id}"
    message = f"""<!DOCTYPE html>
                <html>
                <head>
                    <style>
                        body {{
                            font-family: Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                        }}
                        .container {{
                            max-width: 600px;
                            margin: 20px auto;
                            padding: 20px;
                            border: 1px solid #e1e1e1;
                            border-radius: 5px;
                        }}
                        .header {{
                            color: #d9534f;
                            font-size: 18px;
                            font-weight: bold;
                            margin-bottom: 20px;
                        }}
                        .detail-row {{
                            margin-bottom: 10px;
                        }}
                        .label {{
                            font-weight: bold;
                            display: inline-block;
                            width: 180px;
                        }}
                        .footer {{
                            margin-top: 20px;
                            font-size: 12px;
                            color: #777;
                        }}
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="header">⚠️ Payment Transaction Failed</div>
                        
                        <div class="detail-row">
                            <span class="label">Subject:</span>
                            <span>{transaction.order_id}: Payment failed (Transaction ID: {transaction.provider_transaction_id})</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="label">User:</span>
                            <span>{user.fullName}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="label">Email:</span>
                            <span>{user.email}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="label">Order ID:</span>
                            <span>{transaction.order_id}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="label">Transaction ID (Provider):</span>
                            <span>{transaction.provider_transaction_id}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="label">Payment ID (Provider):</span>
                            <span>{transaction.provider_payment_id}</span>
                        </div>
                        
                        <div class="detail-row">
                            <span class="label">Payment Method:</span>
                            <span>{transaction.payment_method}</span>
                        </div>
                        
                        <div class="detail-row">
                            <div class="label">Provider Data:</div>
                            <pre style="background: #f5f5f5; padding: 10px; border-radius: 3px; overflow-x: auto;">{raw_data}</pre>
                        </div>
                        
                        <div class="footer">
                            <p>This is an automated notification. Please investigate this failed transaction.</p>
                        </div>
                    </div>
                </body>
                </html>"""
    
    
    ticket_message = f"""
        ⚠️ Payment Transaction Failed

        Subject: {transaction.order_id}: Payment failed (Transaction ID: {transaction.provider_transaction_id})

        User Details:
        - Name: {user.fullName}
        - Email: {user.email}

        Order Details:
        - Order ID: {transaction.order_id}
        - Transaction ID (Provider): {transaction.provider_transaction_id}
        - Payment ID (Provider): {transaction.provider_payment_id}
        - Payment Method: {transaction.payment_method}

        This is an automated system note. Please investigate this failed transaction.
        """
    exsiting_support_ticket = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.subject == subject,
            SupportTicket.user_id == user.id,
        )
        .first()
    )
    if exsiting_support_ticket:
        return print("[DEBUG] The Failed payment entry has already been added")

    support_ticket = SupportTicket(
        user_id=user.id,
        subject=subject,
        message=ticket_message,
    )
    db.add(support_ticket)
    db.flush()
    print(f"[DEBUG] Created support ticket with ID: {support_ticket.id}")

    log_entry = ActivityLog(
        user_id=transaction.user_id,
        username=user.fullName,
        role=user.role if user.role else "user",
        action="Payment",
        log_activity=f"Support ticket {support_ticket.id} :Payment error occurred, order id: {transaction.order_id}",
    )
    db.add(log_entry)
    db.flush()
    print(f"[DEBUG] Logged activity with ID: {log_entry.id}")
    # ✅ Fetch current settings
    settings = db.query(Settings).first()

    recipients = [user.email]

    # ✅ Add all admin emails if toggle is ON and emails exist
    if settings and settings.toggle_push_notifications:
        admin_emails = (
            settings.push_notification_admin_emails
            if settings.push_notification_admin_emails
            else []
        )
        # Ensure only valid, non-empty emails are used
        admin_emails = [e.strip() for e in admin_emails if e and e.strip()]
        if admin_emails:
            recipients.extend(admin_emails)

    # ✅ Send email
    send_email(
        subject=subject,
        html_content=message,
        recipients=recipients,
    )
    print(f"[DEBUG] Email sent to: {recipients}")

    print("[DEBUG] Email sent")

    db.commit()
    print("[DEBUG] DB commit successful")




router = APIRouter(prefix="/settings", tags=["Settings"])

# -----------------------------
# get settings
# -----------------------------
@router.get("/", response_model=SettingsRead)
def get_settings(db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")
    return settings

# -----------------------------
# Add new settings
# -----------------------------
@router.post("/", response_model=SettingsRead)
def upsert_settings(data: SettingsCreate, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()

    if not settings:
        settings = Settings(**data.dict())
        db.add(settings)
    else:
        for field, value in data.dict().items():
            setattr(settings, field, value)

    db.commit()
    db.refresh(settings)
    return settings

# -----------------------------
# Update settings
# -----------------------------
@router.patch("/", response_model=SettingsRead)
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    update_data = data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(settings, field, value)

    db.commit()
    db.refresh(settings)
    return settings


# -----------------------------
# Add an email
# -----------------------------
@router.post("/add-email", response_model=SettingsRead)
def add_email(email: EmailStr, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    # Initialize list if None
    if not settings.push_notification_admin_emails:
        settings.push_notification_admin_emails = []

    normalized_email = email.strip().lower()
    existing_emails = [e.lower() for e in settings.push_notification_admin_emails]

    if normalized_email in existing_emails:
        raise HTTPException(status_code=400, detail="Email already exists")

    # ✅ Reassign JSON field (so SQLAlchemy tracks change)
    updated_emails = settings.push_notification_admin_emails.copy()
    updated_emails.append(normalized_email)
    settings.push_notification_admin_emails = updated_emails

    db.commit()
    db.refresh(settings)
    return settings



# -----------------------------
# Remove an email
# -----------------------------
@router.delete("/remove-email", response_model=SettingsRead)
def remove_email(email: EmailStr, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    if not settings.push_notification_admin_emails:
        raise HTTPException(status_code=400, detail="No admin emails found")

    normalized_email = email.strip().lower()
    existing_emails = [e.lower() for e in settings.push_notification_admin_emails]

    if normalized_email not in existing_emails:
        raise HTTPException(status_code=400, detail="Email not found")

    # ✅ Remove by index to preserve original case if needed
    index = existing_emails.index(normalized_email)
    updated_emails = settings.push_notification_admin_emails.copy()
    updated_emails.pop(index)
    settings.push_notification_admin_emails = updated_emails

    db.commit()
    db.refresh(settings)
    return settings



# -----------------------------
# Edit an existing email
# -----------------------------
@router.put("/edit-email", response_model=SettingsRead)
def edit_email(old_email: EmailStr, new_email: EmailStr, db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    if not settings.push_notification_admin_emails:
        raise HTTPException(status_code=400, detail="No admin emails found")

    normalized_old = old_email.strip().lower()
    normalized_new = new_email.strip().lower()
    existing_emails = [e.lower() for e in settings.push_notification_admin_emails]

    if normalized_old not in existing_emails:
        raise HTTPException(status_code=400, detail="Old email not found")

    if normalized_new in existing_emails:
        raise HTTPException(status_code=400, detail="New email already exists")

    # ✅ Replace old with new (case-insensitive)
    index = existing_emails.index(normalized_old)
    updated_emails = settings.push_notification_admin_emails.copy()
    updated_emails[index] = normalized_new
    settings.push_notification_admin_emails = updated_emails

    db.commit()
    db.refresh(settings)
    return settings


# -----------------------------
# Toggle push notifications
# -----------------------------
@router.patch("/toggle", response_model=SettingsRead)
def toggle_push_notifications(db: Session = Depends(get_db)):
    settings = db.query(Settings).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Add an email first. to activiate notifications")

    # ✅ Ensure toggle ON only if emails exist
    if not settings.push_notification_admin_emails or len(settings.push_notification_admin_emails) == 0:
        if settings.toggle_push_notifications:  # if already ON, allow turning OFF
            settings.toggle_push_notifications = False
            db.commit()
            db.refresh(settings)
            return settings
        else:
            raise HTTPException(
                status_code=400,
                detail="Cannot enable push notifications — no admin emails configured",
            )

    # ✅ Otherwise, toggle normally
    settings.toggle_push_notifications = not settings.toggle_push_notifications
    db.commit()
    db.refresh(settings)
    return settings
