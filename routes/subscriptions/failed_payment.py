from sqlalchemy.orm import Session
from models.activityLogModel.activityLogModel import ActivityLog
from models.authModel.authModel import AuthUser
from models.subscriptions.transactionModel import Transaction
from models.supportTickets.models import SupportTicket
from send_email import send_email


def handle_failed_payment(transaction_id: int, order_id: str, raw_data, db: Session):
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
        message=message,
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
    send_email(
        subject=subject,
        html_content=message,
        recipients=[user.email, "gurdeep@devexhub.in"],
    )
    print("[DEBUG] Email sent")

    db.commit()
    print("[DEBUG] DB commit successful")
