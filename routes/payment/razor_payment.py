import random
import hmac
import hashlib
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import requests
from dotenv import load_dotenv

from config import get_db
from models.adminModel.adminModel import SubscriptionPlans
from models.authModel.authModel import AuthUser
from models.subscriptions.userCredits import UserCredits
from routes.subscriptions.transactions import create_transaction, update_transaction
from routes.subscriptions.user_credits import create_user_credit_entry, update_user_credit_entry_topup
from routes.subscriptions.token_usage import create_token_usage, update_token_usage_topup
from routes.subscriptions.failed_payment import handle_failed_payment
from utils.utils import get_country_from_ip, decode_access_token
from models.authModel.authModel import AuthUser
from models.paymentModel.paymentModel import (
    PaymentVerificationRequest,
    PaymentOrderRequest,
)
router = APIRouter()
load_dotenv()

# Razorpay Configuration
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")
RAZORPAY_ENV = os.getenv("RAZORPAY_ENV", "TEST")
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"

# Request/Response Models
class RazorpayOrderRequest(BaseModel):
    customer_id: int
    plan_id: Optional[int] = None
    credit: Optional[float] = None
    return_url: str = Field(default="https://yashraa.ai/dashboard")

class RazorpayVerificationRequest(BaseModel):
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str

# Utility Functions
def generate_razorpay_auth():
    """Generate basic auth for Razorpay API requests"""
    import base64
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise ValueError("Razorpay credentials not properly configured")
    
    credentials = f"{RAZORPAY_KEY_ID}:{RAZORPAY_KEY_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded_credentials}"

def generate_razorpay_headers():
    """Generate headers for Razorpay API requests"""
    return {
        "Authorization": generate_razorpay_auth(),
        "Content-Type": "application/json",
    }

def generate_order_id() -> str:
    """Generate unique order ID"""
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    return f"rz_{timestamp_ms}_{random.randint(1000, 9999)}"

def verify_razorpay_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Verify Razorpay payment signature"""
    if not RAZORPAY_KEY_SECRET:
        raise ValueError("Razorpay key secret not configured")
    
    # Create the signature string
    message = f"{order_id}|{payment_id}"
    
    # Generate HMAC signature
    generated_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(generated_signature, signature)

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify Razorpay webhook signature"""
    if not RAZORPAY_WEBHOOK_SECRET:
        raise ValueError("Razorpay webhook secret not configured")
    
    generated_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(generated_signature, signature)

# API Endpoints
@router.post("/create-order-razorpay")
async def create_razorpay_order(
    request: Request, 
    order_data: RazorpayOrderRequest, 
    db: Session = Depends(get_db),
    
):
    """Create a payment order in Razorpay"""
    url = f"https://api.razorpay.com/v1/orders"
    client_ip = request.client.host
    print(" this part is working")
    # Validate environment variables
    if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Razorpay credentials not configured",
        )

    print(f"Razorpay Configuration - Key ID: {RAZORPAY_KEY_ID}, Env: {RAZORPAY_ENV}")

    # Get user details
    user = db.query(AuthUser).filter(AuthUser.id == order_data.customer_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")

    amount = 0
    plan_id = None
    transaction_type = None
    country = await get_country_from_ip(ip=client_ip)
    currency = "USD"

    print(f"Country detected: {country}")

    # Handle plan subscription
    if order_data.plan_id:
        plan = db.query(SubscriptionPlans).filter(
            SubscriptionPlans.id == order_data.plan_id
        ).first()

        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        amount = plan.pricingDollar
        if country == "IN":
            amount = plan.pricingInr
            currency = "INR"
        
        plan_id = plan.id
        transaction_type = "plan"

    # Handle credit top-up
    if order_data.credit:
        amount = order_data.credit
        transaction_type = "topup"
        
        if country == "IN":
            currency = "INR"

        credit = db.query(UserCredits).filter_by(user_id=user.id).first()
        if not credit:
            raise HTTPException(status_code=404, detail="No active plan found")

        if credit.expiry_date < datetime.now():
            raise HTTPException(
                status_code=404,
                detail="Current plan is expired. No active plan to add credits",
            )

        plan_id = credit.plan_id

    if not (order_data.plan_id or order_data.credit):
        raise HTTPException(
            status_code=400, 
            detail="Either plan_id or credit must be provided"
        )

    # Convert amount to paise (smallest currency unit) for INR
    # Razorpay expects amount in paise for INR and cents for USD
    razorpay_amount = int(amount * 100)
    print("this part is also working")
    # Generate unique receipt/order ID
    receipt_id = generate_order_id()

    payload = {
        "amount": razorpay_amount,
        "currency": currency,
        "receipt": receipt_id,
        # "callback_url": "https://3b31ceb1f109.ngrok-free.app/razorpay",  
        # "redirect":True,
        # "redirect_url": "https://yourdomain.com/payment/failed",
        "notes": {
            "customer_id": str(order_data.customer_id),
            "customer_name": user.fullName,
            "customer_email": user.email,
            "transaction_type": transaction_type,
            "plan_id": str(plan_id) if plan_id else None,
        }
    }

    print("Creating Razorpay order with payload:", json.dumps(payload, indent=2))

    headers = generate_razorpay_headers()
    print(headers)
    print("RAZORPAY_KEY_ID:", RAZORPAY_KEY_ID)
    print("RAZORPAY_KEY_SECRET:", RAZORPAY_KEY_SECRET)

    try:
        response = requests.post(url, json=payload, headers=headers)
        print(response)
        print("Razorpay Response Status: {response.status_code}")
        print("Razorpay Response Body: {response.text}")

        if response.status_code != 200:
            print(f"Razorpay API Error: {response.status_code} - {response.text}")
            
            try:
                error_data = response.json()
                error_message = error_data.get("error", {}).get("description", "Razorpay API request failed")
                error_code = error_data.get("error", {}).get("code", "UNKNOWN")

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": error_message,
                        "code": error_code,
                        "status_code": response.status_code,
                    },
                )
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Razorpay API request failed",
                        "status_code": response.status_code,
                        "response": response.text,
                    },
                )
        print("---------------------------------------------------------------------")
        razorpay_response = response.json()

        # Validate response
        if "id" not in razorpay_response:
            print(f"Invalid Razorpay response: {razorpay_response}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Razorpay did not return a valid order ID",
            )

        print("RAZORPAY RESPONSE: ", razorpay_response)

        # Create transaction record in database
        new_transaction = await create_transaction(
            db=db,
            provider="razorpay",
            order_id=razorpay_response["receipt"],  # Using receipt as our order_id
            user_id=order_data.customer_id,
            amount=amount,  # Store original amount (not in paise)
            currency=currency,
            type=transaction_type,
            plan_id=plan_id,
            status="created",
            provider_payment_id=razorpay_response["id"],  # Razorpay order ID
        )
        print("Transaction created successfully!")


        # Return response for frontend
        response= {
            "success": True,
            "razorpay_order_id": razorpay_response["id"],
            "razorpay_key_id": RAZORPAY_KEY_ID,
            "amount": razorpay_response["amount"],
            "currency": razorpay_response["currency"],
            "receipt": razorpay_response["receipt"],
            "status": razorpay_response["status"],
            "customer_details": {
                "name": user.fullName,
                "email": user.email,
            },
            "message": "Order created successfully",
        }
        print("Response prepared:", response)
        print("create order compeleted")
        return response

    except requests.exceptions.RequestException as e:
        print("Request Exception:", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Network error while creating payment order: {str(e)}",
        )
    except Exception as e:
        print("Unexpected error:", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=str(e)
        )

# @router.post("/verify-payment")
# async def verify_razorpay_payment(
#     request: Request,  # Add request parameter
#     verification_data: RazorpayVerificationRequest,
#     db: Session = Depends(get_db)
      

# ):
#     """Verify Razorpay payment"""
#     try:
#         # Verify signature
#         is_valid = verify_razorpay_signature(
#             verification_data.razorpay_order_id,
#             verification_data.razorpay_payment_id,
#             verification_data.razorpay_signature
#         )

#         if not is_valid:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Invalid payment signature"
#             )

#         # Fetch payment details from Razorpay
#         payment_url = f"{RAZORPAY_BASE_URL}/payments/{verification_data.razorpay_payment_id}"
#         headers = generate_razorpay_headers()
        
        # response = requests.get(payment_url, headers=headers)
        
#         if response.status_code != 200:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Failed to fetch payment details from Razorpay"
#             )

#         payment_data = response.json()
        
#         # Map Razorpay status to our status
#         status_map = {
#             "captured": "success",
#             "authorized": "pending",
#             "failed": "failed",
#             "refunded": "refunded",
#         }
        
#         payment_status = status_map.get(payment_data.get("status"), "unknown")

#         # Update transaction in database
#         transaction = await update_transaction(
#             db=db,
#             provider_payment_id=verification_data.razorpay_order_id,
#             status=payment_status,
#             provider_transaction_id=verification_data.razorpay_payment_id,
#             payment_method=payment_data.get("method"),
#             raw_data=payment_data,
#         )

#         # Process successful payment
#         if payment_status == "success":
#             transaction_type = payment_data.get("notes", {}).get("transaction_type")
            
#             if transaction_type == "plan":
#                 user_credit = create_user_credit_entry(trans_id=transaction.id, db=db)
#                 success, token_entries = create_token_usage(
#                     credit_id=user_credit.id, 
#                     transaction_id=transaction.id, 
#                     db=db
#                 )
#             elif transaction_type == "topup":
#                 user_credit = update_user_credit_entry_topup(trans_id=transaction.id, db=db)
#                 success, token_entries = update_token_usage_topup(
#                     credit_id=user_credit.id, 
#                     transaction_id=transaction.id, 
#                     db=db
#                 )

#             return {
#                 "success": True,
#                 "status": "payment_verified",
#                 "payment_data": payment_data,
#                 "token_entries": token_entries if 'token_entries' in locals() else None,
#             }
#         else:
#             return {
#                 "success": False,
#                 "status": payment_status,
#                 "payment_data": payment_data,
#             }

#     except Exception as e:
#         print(f"Payment verification error: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Payment verification failed: {str(e)}"
#         )

# @router.post("/razorpay")
# async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
#     """Handle Razorpay webhooks"""
#     print("web book")
#     try:
#         # Get raw body and signature
#         headers = dict(request.headers)
#         print("HEADERS:", json.dumps(headers, inden=2))
#         raw_body = await request.body()
#         print("RAW BODY:", raw_body.decode())
#         signature = request.headers.get("x-razorpay-signature")
#         print("raw_body",raw_body);
#         print("signature",signature);
#         if not signature:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Missing webhook signature"
#             )

#         # Verify webhook signature
#         if not verify_webhook_signature(raw_body, signature):
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Invalid webhook signature"
#             )

#         # Parse payload
#         payload = json.loads(raw_body.decode("utf-8"))
        
#         return await process_razorpay_webhook_payload(payload, db)

#     except json.JSONDecodeError:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Invalid JSON payload"
#         )
#     except Exception as e:
#         print(f"Webhook processing error: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Webhook processing failed: {str(e)}"
#         )

# async def process_razorpay_webhook_payload(payload: Dict[str, Any], db: Session):
#     """Process Razorpay webhook payload"""
#     event_type = payload.get("event")
#     entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    
#     print(f"Processing Razorpay webhook event: {event_type}")
#     print(f"Entity data: {entity}")

#     # Map event types to actions
#     if event_type == "payment.captured":
#         return await handle_payment_success(entity, db)
#     elif event_type == "payment.failed":
#         return await handle_payment_failure(entity, db)
#     elif event_type == "payment.authorized":
#         return await handle_payment_authorized(entity, db)
#     else:
#         print(f"Unhandled webhook event: {event_type}")
#         return {"status": "unhandled_event", "event": event_type}

async def handle_payment_success(entity: Dict[str, Any], db: Session):
    """Handle successful payment webhook"""
    try:
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        
        # Update transaction
        transaction = await update_transaction(
            db=db,
            provider_payment_id=order_id,
            provider_transaction_id=payment_id,
            status="success",
            payment_method=entity.get("method"),
            raw_data=entity,
        )

        # Get transaction type from notes
        notes = entity.get("notes", {})
        transaction_type = notes.get("transaction_type")

        # Process based on transaction type
        if transaction_type == "plan":
            user_credit = create_user_credit_entry(trans_id=transaction.id, db=db)
            success, token_entries = create_token_usage(
                credit_id=user_credit.id, 
                transaction_id=transaction.id, 
                db=db
            )
        elif transaction_type == "topup":
            user_credit = update_user_credit_entry_topup(trans_id=transaction.id, db=db)
            success, token_entries = update_token_usage_topup(
                credit_id=user_credit.id, 
                transaction_id=transaction.id, 
                db=db
            )

        return {
            "success": True,
            "message": "Payment processed successfully",
            "token_entries": token_entries if 'token_entries' in locals() else None,
        }

    except Exception as e:
        print(f"Error handling payment success: {str(e)}")
        return {"success": False, "error": str(e)}

async def handle_payment_failure(entity: Dict[str, Any], db: Session):
    """Handle failed payment webhook"""
    try:
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        
        # Update transaction
        transaction = await update_transaction(
            db=db,
            provider_payment_id=order_id,
            provider_transaction_id=payment_id,
            status="failed",
            payment_method=entity.get("method"),
            raw_data=entity,
        )

        # Handle failed payment (create support ticket, etc.)
        handle_failed_payment(
            transaction_id=transaction.id,
            order_id=None,
            raw_data=entity,
            db=db
        )

        return {
            "success": True,
            "message": "Failed payment processed",
        }

    except Exception as e:
        print(f"Error handling payment failure: {str(e)}")
        return {"success": False, "error": str(e)}

async def handle_payment_authorized(entity: Dict[str, Any], db: Session):
    """Handle authorized payment webhook"""
    try:
        order_id = entity.get("order_id")
        payment_id = entity.get("id")
        
        # Update transaction to pending status
        await update_transaction(
            db=db,
            provider_payment_id=order_id,
            provider_transaction_id=payment_id,
            status="pending",
            payment_method=entity.get("method"),
            raw_data=entity,
        )

        return {
            "success": True,
            "message": "Payment authorized, waiting for capture",
        }

    except Exception as e:
        print(f"Error handling payment authorization: {str(e)}")
        return {"success": False, "error": str(e)}

@router.get("/is-international")
async def check_international_payment(request: Request):
    """Check if payment should use international gateway"""
    try:
        client_ip = request.client.host
        print(f"Client IP: {client_ip}")
        
        country = await get_country_from_ip(ip=client_ip)
        print(f"Detected country: {country}")
        
        is_international = country != "IN"
        
        return {
            "is_international": is_international,
            "country": country,
            "currency": "USD" if is_international else "INR"
        }
        
    except Exception as e:
        print(f"Error detecting country: {e}")
        # Default to international if detection fails
        return {
            "is_international": True,
            "country": "UNKNOWN",
            "currency": "USD"
        }