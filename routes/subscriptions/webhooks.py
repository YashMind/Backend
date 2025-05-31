from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from config import get_db, settings
import hashlib
import base64
import json

import hmac

from models.subscriptions.transactionModel import Transaction

router = APIRouter(prefix="/webhook/payments")


async def generateCashfreeSignature(request:Request):
    raw_body = await request.body()

    print("Cashfree raw body", raw_body.data)
    timestamp = request.headers['x-webhook-timestamp']
    signature = request.headers['x-webhook-signature']
    signatureData = timestamp+raw_body.data
    message = bytes(signatureData, 'utf-8')
    secretkey=bytes("<client-signature>",'utf-8')
    generatedSignature = base64.b64encode(hmac.new(secretkey, message, digestmod=hashlib.sha256).digest())
    computed_signature = str(generatedSignature, encoding='utf8')
    if computed_signature == signature:
        json_response = json.loads(raw_body.data)
        return json_response
    raise Exception("Generated signature and received signature did not match.")

async def update_transaction(
    db: Session,
    provider: str,
    order_id: str = None,
    provider_transaction_id: str = None,
    status: str = None,
    payment_method: str = None,
    payment_method_details: dict = None,
    fees: float = None,
    tax: float = None,
    raw_data: dict = None
):
    # Find transaction
    transaction = None
    if order_id:
        transaction = db.query(Transaction).filter_by(
            provider=provider, 
            order_id=order_id
        ).first()
    if not transaction and provider_transaction_id:
        transaction = db.query(Transaction).filter_by(
            provider=provider,
            provider_transaction_id=provider_transaction_id
        ).first()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Update provider ID if missing
    if provider_transaction_id and not transaction.provider_transaction_id:
        transaction.provider_transaction_id = provider_transaction_id

    # Update status if provided and valid
    valid_statuses = ["created", "pending", "success", "failed", "refunded", "cancelled"]
    if status and status in valid_statuses:
        transaction.status = status
        # Set completion time for terminal states
        if status in ("success", "failed", "refunded", "cancelled"):
            transaction.completed_at = datetime.now(timezone.utc)

    # Update payment details
    if payment_method:
        transaction.payment_method = payment_method
    if payment_method_details:
        transaction.payment_method_details = payment_method_details
    if fees is not None:
        transaction.fees = fees
    if tax is not None:
        transaction.tax = tax
    if raw_data:
        transaction.provider_data = raw_data

    # Commit changes
    try:
        db.commit()
        db.refresh(transaction)
        return JSONResponse(content={"status": "updated"}, status_code=200)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")
    

async def process_cashfree_payload(payload: dict, db: Session):
    # Extract data from Cashfree payload
    order_id = payload.get("orderId")
    provider_transaction_id = payload.get("referenceId")
    tx_status = payload.get("txStatus")
    
    # Map status to your schema
    status_map = {
        "SUCCESS": "success",
        "FAILED": "failed",
        "PENDING": "pending",
        "USER_DROPPED": "cancelled",
        "REFUND": "refunded"
    }
    status = status_map.get(tx_status)
    
    # Update transaction
    return await update_transaction(
        db=db,
        provider="cashfree",
        order_id=order_id,
        provider_transaction_id=provider_transaction_id,
        status=status,
        payment_method=payload.get("paymentMode"),
        raw_data=payload
    )

async def process_paypal_payload(payload: dict, db: Session):
    resource = payload.get("resource", {})
    event_type = payload.get("event_type", "")
    
    if "PAYMENT.CAPTURE" in event_type:
        status_map = {
            "COMPLETED": "success",
            "DECLINED": "failed",
            "PENDING": "pending",
            "REFUNDED": "refunded",
            "CANCELLED": "cancelled"
        }
        status = status_map.get(resource.get("status"))
        
        # Extract payment details
        payment_source = resource.get("payment_source", {})
        payment_method, details = None, None
        if "card" in payment_source:
            payment_method = "card"
            details = {
                "last_digits": payment_source["card"].get("last_digits"),
                "brand": payment_source["card"].get("brand")
            }
        elif "paypal" in payment_source:
            payment_method = "paypal"
            details = {"email": payment_source["paypal"].get("email_address")}
        
        # Update transaction
        return await update_transaction(
            db=db,
            provider="paypal",
            order_id=resource.get("custom_id"),
            provider_transaction_id=resource.get("id"),
            status=status,
            payment_method=payment_method,
            payment_method_details=details,
            fees=float(resource.get("seller_receivable_breakdown", {}).get("paypal_fee", {}).get("value", 0)),
            raw_data=payload
        )
    return JSONResponse(content={"status": "unhandled_event"}, status_code=200)
    
# CashFree Webhook Handler
@router.post("/cashfree")
async def cashfree_webhook(request: Request, db: Session = Depends(get_db)):

    print("CASHFREE PAYLOAD RECIEVED: ", request)
    # Verify signature

    payload = await generateCashfreeSignature(request=request)
    return await process_cashfree_payload(payload, db)

# PayPal Webhook Handler
@router.post("/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    # Verify PayPal webhook (implementation depends on PayPal SDK)
    try:
        # This is a placeholder - implement actual verification
        payload = await request.json()
        return await process_paypal_payload(payload, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

