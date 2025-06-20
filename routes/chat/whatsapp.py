import re
from fastapi import (
    APIRouter,
    Depends,
    Form,
    Query,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
import httpx  # Replaced requests with httpx for async
import logging
from config import Settings, get_db
from models.authModel.authModel import AuthUser
from models.chatModel.chatModel import ChatBots
from models.chatModel.integrations import WhatsAppUser
from utils.utils import decode_access_token, get_response_from_chatbot
import os
from decorators.product_status import check_product_status
from typing import Annotated, Optional
from pydantic import BaseModel, Field
import hmac
import hashlib
from cryptography.fernet import Fernet  # For token encryption

router = APIRouter(tags=["WhatsApp Integration"])
logger = logging.getLogger(__name__)

# --- Models ---
PhoneNumber = Annotated[str, Field(pattern=r"^\d{5,15}$", examples=["1234567890"])]


class WhatsAppRegisterRequest(BaseModel):
    bot_id: int
    whatsapp_number: PhoneNumber
    access_token: str
    phone_number_id: str
    business_account_id: str
    webhook_secret: Optional[str] = None  # Per-user webhook secret


class MessageRequest(BaseModel):
    bot_id: int  # Added to specify which bot sends the message
    to_number: PhoneNumber
    message: str
    template_name: Optional[str] = None
    language_code: Optional[str] = "en_US"  # Default to en_US


class WhatsAppUpdateRequest(BaseModel):
    access_token: Optional[str] = None
    phone_number_id: Optional[str] = None
    business_account_id: Optional[str] = None
    webhook_secret: Optional[str] = None
    is_active: Optional[bool] = None


# --- Constants ---
WHATSAPP_API_URL = "https://graph.facebook.com/v22.0/"
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
fernet = Fernet(ENCRYPTION_KEY)


# --- API Endpoints ---
@router.post("/register", status_code=status.HTTP_201_CREATED)
@check_product_status("chatbot")
async def register_whatsapp_user(
    request: Request,
    request_data: WhatsAppRegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register a WhatsApp business account for a specific user.
    """
    logger.info("Received WhatsApp registration request.")

    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    logger.info(f"Decoded user ID from token: {user_id}")
    logger.debug(f"Registration request data: {request_data}")

    if not user_owns_bot(user_id, request_data.bot_id, db=db):
        logger.warning(
            f"User {user_id} attempted to register bot {request_data.bot_id} without ownership."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to register this bot",
        )
    whatsapp_number = re.sub(r"\D", "", request_data.whatsapp_number)
    existing = db.query(WhatsAppUser).filter_by(whatsapp_number=whatsapp_number).first()

    if existing:
        logger.warning(
            f"Attempt to re-register an existing WhatsApp number: {request_data.whatsapp_number}"
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Number already registered with some another bot.",
        )

    logger.info(
        f"Verifying WhatsApp credentials for phone_number_id={request_data.phone_number_id}"
    )
    verify_url = f"{WHATSAPP_API_URL}{request_data.phone_number_id}"
    headers = {
        "Authorization": f"Bearer {request_data.access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(verify_url, headers=headers)
            response.raise_for_status()
            account_info = response.json()
            logger.debug(f"WhatsApp API response: {account_info}")

            if str(account_info.get("id")) != request_data.phone_number_id:
                logger.error("Phone number ID mismatch with WhatsApp API response.")
                raise ValueError("Phone number ID mismatch")
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"WhatsApp verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid WhatsApp credentials",
            )

    encrypted_token = fernet.encrypt(request_data.access_token.encode()).decode()
    logger.info(f"Encrypted access token for {request_data.whatsapp_number}")

    try:
        new_user = WhatsAppUser(
            bot_id=request_data.bot_id,
            whatsapp_number=whatsapp_number,
            access_token=encrypted_token,
            phone_number_id=request_data.phone_number_id,
            business_account_id=request_data.business_account_id,
            webhook_secret=request_data.webhook_secret,
            is_active=True,
            opt_in_date=datetime.utcnow(),
        )
        db.add(new_user)
        db.commit()
        logger.info(
            f"Successfully registered WhatsApp number: {request_data.whatsapp_number}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Database error while saving WhatsApp user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register number",
        )

    return {"status": "success", "message": "WhatsApp number registered"}


@router.post("/send-message")
async def send_whatsapp_message(
    request: Request,
    request_data: MessageRequest,
    db: Session = Depends(get_db),
):
    """Send message to WhatsApp user from a specific bot"""
    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))
    # Verify user owns the bot_id
    if not user_owns_bot(user_id, request_data.bot_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized to use this bot"
        )

    # Get sender credentials
    sender = (
        db.query(WhatsAppUser)
        .filter_by(bot_id=request_data.bot_id, is_active=True)
        .first()
    )

    if not sender:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active WhatsApp account registered for this bot",
        )

    # Decrypt access token
    access_token = fernet.decrypt(sender.access_token.encode()).decode()

    # Prepare API request_data
    url = f"{WHATSAPP_API_URL}{sender.phone_number_id}/messages"
    headers = {"Content-Type": "application/json"}

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": request_data.to_number,
        "type": "text",
        "text": {"body": request_data.message},
    }

    if request_data.template_name:
        payload = {
            "messaging_product": "whatsapp",
            "to": request_data.to_number,
            "type": "template",
            "template": {
                "name": request_data.template_name,
                "language": {"code": request_data.language_code},
            },
        }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            # Update stats
            sender.message_count += 1  # Fixed increment
            sender.last_message_at = datetime.utcnow()
            db.commit()

            return {
                "status": "success",
                "message_id": response.json().get("messages")[0]["id"],
            }
        except httpx.RequestError as e:
            error_detail = (
                response.json().get("error", {}).get("message", "Unknown error")
                if response
                else str(e)
            )
            logger.error(f"Message failed: {error_detail}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Message failed: {error_detail}",
            )


@router.get("/webhook")
async def verify_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    db: Session = Depends(get_db),
):
    """Verify webhook endpoint during setup"""
    print("Webhook Verification Params:", hub_mode, hub_challenge, hub_verify_token)
    user = db.query(WhatsAppUser).filter_by(webhook_secret=hub_verify_token).first()
    if hub_mode == "subscribe" and user:
        return Response(content=hub_challenge, media_type="text/plain")
    return Response(status_code=status.HTTP_403_FORBIDDEN)


@router.post("/webhook")
async def handle_incoming_message(request: Request, db: Session = Depends(get_db)):
    """Handle incoming WhatsApp messages and statuses"""
    # Get payload to extract phone_number_id for signature verification
    payload = await request.json()
    entry = payload.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0]
    value = changes.get("value", {})
    recipient_phone_id = value.get("metadata", {}).get("phone_number_id")

    # print(f"phone number id: {recipient_phone_id}, entry: {entry}, changes: {changes}, value: {value}")

    # Find user to get webhook secret
    user = db.query(WhatsAppUser).filter_by(phone_number_id=recipient_phone_id).first()
    # if not user or not await verify_whatsapp_signature(request, user.webhook_secret):
    if not user:
        return Response(status_code=status.HTTP_401_UNAUTHORIZED)

    # Handle message or status updates
    if "messages" in value:
        message_data = value.get("messages", [{}])[0]
        from_number = message_data.get("from", "")
        message_body = message_data.get("text", {}).get("body", "")

        if not from_number or not message_body:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)

        try:
            # Get bot response
            response_text = get_response_from_chatbot(
                data={
                    "message": message_body,
                    "bot_id": user.bot_id,
                    "token": f"from:{user.whatsapp_number},to:{from_number}",
                },
                platform="whatsapp",
                db=db,
            )

            # Decrypt access token
            access_token = fernet.decrypt(user.access_token.encode()).decode()
            # access_token = user.access_token.encode()

            # Send reply
            send_url = f"{WHATSAPP_API_URL}{user.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": from_number,
                "type": "text",
                "text": {"body": response_text},
            }

            async with httpx.AsyncClient() as client:
                await client.post(send_url, json=payload, headers=headers)

            # Update stats
            user.message_count += 1  # Fixed increment
            user.last_message_at = datetime.utcnow()
            db.commit()

            return Response(status_code=status.HTTP_200_OK)
        except Exception as e:
            logger.exception("Error handling incoming message")
            return Response(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

    elif "statuses" in value:
        # Handle message status updates (e.g., sent, delivered, read)
        status_data = value.get("statuses", [{}])[0]
        message_id = status_data.get("id")
        status_type = status_data.get("status")
        # Update database with status (implement as needed)
        logger.info(f"Message {message_id} status: {status_type}")
        return Response(status_code=status.HTTP_200_OK)

    return Response(status_code=status.HTTP_400_BAD_REQUEST)


async def verify_whatsapp_signature(request: Request, webhook_secret: str) -> bool:
    """Verify WhatsApp webhook signature"""
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not signature or not signature.startswith("sha256="):
        logger.warning(f"Invalid or missing X-Hub-Signature-256 header: {signature}")
        return False

    body = await request.body()
    secret = webhook_secret.encode()
    expected = hmac.new(secret, body.decode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(f"sha256={expected}", signature):
        logger.warning(
            f"Signature verification failed for webhook. Expected: sha256={expected}, Received: {signature}"
        )
        return False


def user_owns_bot(user_id: int, bot_id: int, db: Session) -> bool:
    # Replace with actual logic to verify bot ownership
    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if not user:
        return False
    bot = (
        db.query(ChatBots)
        .filter(ChatBots.id == bot_id, ChatBots.user_id == user_id)
        .first()
    )
    if not bot:
        return False

    return True  # Example


@router.delete("/delete/{bot_id}", status_code=status.HTTP_200_OK)
@check_product_status("chatbot")
async def delete_whatsapp_registration(
    bot_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Delete WhatsApp registration for a specific bot
    """
    logger.info(f"Deleting WhatsApp registration for bot {bot_id}")

    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    if not user_owns_bot(user_id, bot_id, db=db):
        logger.warning(
            f"User {user_id} attempted to delete bot {bot_id} without ownership"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to delete this bot",
        )

    whatsapp_user = db.query(WhatsAppUser).filter_by(bot_id=bot_id).first()

    if not whatsapp_user:
        logger.info(f"No active WhatsApp registration found for bot {bot_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active WhatsApp registration found",
        )

    try:
        db.delete(whatsapp_user)
        db.commit()
        logger.info(f"Successfully deleted WhatsApp registration for bot {bot_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error while deactivating WhatsApp user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate registration",
        )

    return {"status": "success", "message": "WhatsApp registration deactivated"}


@router.get("/{bot_id}", status_code=status.HTTP_200_OK)
@check_product_status("chatbot")
async def get_whatsapp_registration(
    bot_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get WhatsApp registration details for a specific bot
    """
    logger.info(f"Fetching WhatsApp registration for bot {bot_id}")

    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    if not user_owns_bot(user_id, bot_id, db=db):
        logger.warning(
            f"User {user_id} attempted to access bot {bot_id} without ownership"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to access this bot",
        )

    whatsapp_user = db.query(WhatsAppUser).filter_by(bot_id=bot_id).first()

    if not whatsapp_user:
        logger.info(f"No active WhatsApp registration found for bot {bot_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active WhatsApp registration found",
        )

    # Return the data without the encrypted token for security
    return {
        "whatsapp_number": whatsapp_user.whatsapp_number,
        "phone_number_id": whatsapp_user.phone_number_id,
        "business_account_id": whatsapp_user.business_account_id,
        "webhook_secret": whatsapp_user.webhook_secret,
        "is_active": whatsapp_user.is_active,
        "opt_in_date": whatsapp_user.opt_in_date,
    }


@router.put("/{bot_id}", status_code=status.HTTP_200_OK)
@check_product_status("chatbot")
async def update_whatsapp_registration(
    bot_id: int,
    request_data: WhatsAppUpdateRequest,  # You'll need to create this Pydantic model
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Update WhatsApp registration details for a specific bot
    """
    logger.info(f"Updating WhatsApp registration for bot {bot_id}")

    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    if not user_owns_bot(user_id, bot_id, db=db):
        logger.warning(
            f"User {user_id} attempted to update bot {bot_id} without ownership"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to update this bot",
        )

    whatsapp_user = db.query(WhatsAppUser).filter_by(bot_id=bot_id).first()

    if not whatsapp_user:
        logger.info(f"No WhatsApp registration found for bot {bot_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No WhatsApp registration found",
        )

    # Verify new credentials if provided
    if request_data.access_token or request_data.phone_number_id:
        verify_url = f"{WHATSAPP_API_URL}{request_data.phone_number_id or whatsapp_user.phone_number_id}"
        headers = {
            "Authorization": f"Bearer {request_data.access_token or fernet.decrypt(whatsapp_user.access_token.encode()).decode()}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(verify_url, headers=headers)
                response.raise_for_status()
                account_info = response.json()

                if (
                    request_data.phone_number_id
                    and str(account_info.get("id")) != request_data.phone_number_id
                ):
                    logger.error("Phone number ID mismatch with WhatsApp API response.")
                    raise ValueError("Phone number ID mismatch")
        except (httpx.RequestError, ValueError) as e:
            logger.error(f"WhatsApp verification failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid WhatsApp credentials",
            )

    # Update fields
    try:
        if request_data.access_token:
            whatsapp_user.access_token = fernet.encrypt(
                request_data.access_token.encode()
            ).decode()
        if request_data.phone_number_id:
            whatsapp_user.phone_number_id = request_data.phone_number_id
        if request_data.business_account_id:
            whatsapp_user.business_account_id = request_data.business_account_id
        if request_data.webhook_secret:
            whatsapp_user.webhook_secret = request_data.webhook_secret

        whatsapp_user.is_active = True

        db.commit()
        logger.info(f"Successfully updated WhatsApp registration for bot {bot_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error while updating WhatsApp user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update registration",
        )

    return {"status": "success", "message": "WhatsApp registration updated"}


@router.delete("/{bot_id}", status_code=status.HTTP_200_OK)
@check_product_status("chatbot")
async def deactivate_whatsapp_registration(
    bot_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Deactivate WhatsApp registration for a specific bot
    """
    logger.info(f"Deactivating WhatsApp registration for bot {bot_id}")

    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    if not user_owns_bot(user_id, bot_id, db=db):
        logger.warning(
            f"User {user_id} attempted to deactivate bot {bot_id} without ownership"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to deactivate this bot",
        )

    whatsapp_user = (
        db.query(WhatsAppUser).filter_by(bot_id=bot_id, is_active=True).first()
    )

    if not whatsapp_user:
        logger.info(f"No active WhatsApp registration found for bot {bot_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active WhatsApp registration found",
        )

    try:
        whatsapp_user.is_active = False
        whatsapp_user.opt_out_date = datetime.utcnow()
        db.commit()
        logger.info(f"Successfully deactivated WhatsApp registration for bot {bot_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Database error while deactivating WhatsApp user: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate registration",
        )

    return {"status": "success", "message": "WhatsApp registration deactivated"}
