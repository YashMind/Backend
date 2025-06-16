from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
import requests
import logging
from config import Settings, get_db
from models.chatModel.integrations import WhatsAppUser
from utils.utils import get_response_from_chatbot
import os
from decorators.product_status import check_product_status
from typing import Annotated, Optional
from pydantic import BaseModel, Field
import hmac
import hashlib

router = APIRouter(tags=["WhatsApp Integration"])
logger = logging.getLogger(__name__)

# --- Models ---
PhoneNumber = Annotated[
    str,
    Field(pattern=r"^\d{5,15}$", examples=["1234567890"])  # Removed '+' prefix
]

class WhatsAppRegisterRequest(BaseModel):
    bot_id: int
    whatsapp_number: PhoneNumber
    access_token: str  # WhatsApp permanent access token
    phone_number_id: str  # WhatsApp business phone number ID
    business_account_id: str  # WhatsApp business account ID

class MessageRequest(BaseModel):
    to_number: PhoneNumber  # Recipient number (without country code prefix)
    message: str
    template_name: Optional[str] = None

# --- Constants ---
WHATSAPP_API_URL = "https://graph.facebook.com/v19.0/"
WEBHOOK_VERIFY_TOKEN = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")

# --- API Endpoints ---
@router.post("/register", status_code=status.HTTP_201_CREATED)
@check_product_status("chatbot")
async def register_whatsapp_user(
    request: WhatsAppRegisterRequest,
    db: Session = Depends(get_db)
):
    # Check existing registration
    existing = db.query(WhatsAppUser).filter_by(
        whatsapp_number=request.whatsapp_number
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Number already registered"
        )

    # Verify credentials with WhatsApp
    verify_url = f"{WHATSAPP_API_URL}{request.phone_number_id}"
    headers = {
        "Authorization": f"Bearer {request.access_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(verify_url, headers=headers)
        response.raise_for_status()
        account_info = response.json()
        
        # Validate phone number belongs to business account
        if str(account_info.get("id")) != request.phone_number_id:
            raise ValueError("Phone number ID mismatch")
            
        if str(account_info.get("verified_name")) != request.business_account_id:
            raise ValueError("Business account ID mismatch")
            
    except (requests.RequestException, ValueError) as e:
        logger.error(f"WhatsApp verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid WhatsApp credentials"
        )

    # Save to DB
    try:
        new_user = WhatsAppUser(
            bot_id=request.bot_id,
            whatsapp_number=request.whatsapp_number,
            access_token=request.access_token,
            phone_number_id=request.phone_number_id,
            business_account_id=request.business_account_id,
            is_active=True,
            opt_in_date=datetime.utcnow()
        )
        db.add(new_user)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register number"
        )

    return {"status": "success", "message": "WhatsApp number registered"}

@router.post("/send-message")
async def send_whatsapp_message(
    request: MessageRequest,
    db: Session = Depends(get_db)
):
    """Send message to WhatsApp user"""
    # Get sender credentials (first active bot)
    sender = db.query(WhatsAppUser).filter_by(
        is_active=True
    ).first()
    
    if not sender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active WhatsApp account registered"
        )

    # Prepare API request
    url = f"{WHATSAPP_API_URL}{sender.phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {sender.access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": request.to_number,
        "type": "text",
        "text": {"body": request.message}
    }

    # Handle templates
    if request.template_name:
        payload = {
            "messaging_product": "whatsapp",
            "to": request.to_number,
            "type": "template",
            "template": {
                "name": request.template_name,
                "language": {"code": "en_US"}
            }
        }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        # Update stats
        sender.message_count = WhatsAppUser.message_count + 1
        sender.last_message_at = datetime.utcnow()
        db.commit()

        return {"status": "success", "message_id": response.json().get("messages")[0]["id"]}
    except requests.RequestException as e:
        error_detail = response.json().get("error", {}).get("message", "Unknown error") if response else str(e)
        logger.error(f"Message failed: {error_detail}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Message failed: {error_detail}"
        )

@router.get("/webhook")
async def verify_webhook(
    request: Request,
    hub_mode: str = Form(None),
    hub_challenge: str = Form(None),
    hub_verify_token: str = Form(None)
):
    """Verify webhook endpoint during setup"""
    if hub_mode == "subscribe" and hub_verify_token == WEBHOOK_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=status.HTTP_403_FORBIDDEN)

@router.post("/webhook")
async def handle_incoming_message(
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle incoming WhatsApp messages"""
    # Verify signature
    if not verify_whatsapp_signature(request):
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)
    
    payload = await request.json()
    entry = payload.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0]
    value = changes.get("value", {})
    
    # Extract message details
    message_data = value.get("messages", [{}])[0]
    from_number = message_data.get("from", "")  # Already without prefix
    message_body = message_data.get("text", {}).get("body", "")

    if not from_number or not message_body:
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    try:
        # Find bot associated with recipient number
        recipient_phone_id = value.get("metadata", {}).get("phone_number_id")
        user = db.query(WhatsAppUser).options(joinedload(WhatsAppUser.bot)).filter_by(
            phone_number_id=recipient_phone_id,
            is_active=True
        ).first()
        
        if not user:
            logger.info(f"Message to unregistered number: {recipient_phone_id}")
            return Response(status_code=status.HTTP_404_NOT_FOUND)

        # Get bot response
        response_text = get_response_from_chatbot(
            data={"message": message_body, "bot_id": user.bot_id},
            platform="whatsapp",
            db=db,
        )

        # Send reply
        send_url = f"{WHATSAPP_API_URL}{user.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {user.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": from_number,
            "type": "text",
            "text": {"body": response_text}
        }
        
        requests.post(send_url, json=payload, headers=headers)

        # Update stats
        user.message_count = WhatsAppUser.message_count + 1
        user.last_message_at = datetime.utcnow()
        db.commit()

        return Response(status_code=status.HTTP_200_OK)
    except Exception as e:
        logger.exception("Error handling incoming message")
        return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

async def verify_whatsapp_signature(request: Request) -> bool:
    """Verify WhatsApp webhook signature"""
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature or not signature.startswith("sha256="):
        return False
    
    body = await request.body()
    secret = WEBHOOK_VERIFY_TOKEN.encode()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    
    return hmac.compare_digest(f"sha256={expected}", signature)