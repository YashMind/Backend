from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
    Header,
    Form,
)
from sqlalchemy.orm import Session
import secrets
from datetime import datetime

from config import get_db
from models.authModel.authModel import AuthUser
from models.chatModel.chatModel import ChatBots
from models.chatModel.integrations import ZapierIntegration
from schemas.authSchema.authSchema import User
from utils.utils import get_current_user, get_response_from_chatbot

router = APIRouter()


# 1. Create API Token for Zapier
@router.post("/token")
async def create_zapier_token(
    bot_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        # Verify user owns the bot
        bot = (
            db.query(ChatBots)
            .filter(ChatBots.id == bot_id, ChatBots.user_id == current_user.id)
            .first()
        )
        if not bot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found or you don't have permission",
            )

        return {
            "api_token": bot.token,
            "bot_id": bot_id,
            # "created_at": integration.created_at,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=str(e)
        )  # 1. Create API Token for Zapier


@router.post("/create-integration")
async def create_zapier_integration(
    api_token: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        print("API token : ", api_token)
        # Verify user owns the bot
        bot = db.query(ChatBots).filter(ChatBots.token == api_token).first()
        if not bot:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found or you don't have permission",
            )

        user = db.query(AuthUser).filter(AuthUser.id == bot.user_id).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Store integration details
        integration = ZapierIntegration(
            user_id=user.id,
            bot_id=bot.id,
            api_token=api_token,
            email=user.email,
            created_at=datetime.utcnow(),
        )

        db.add(integration)
        db.commit()

        return {
            "api_token": api_token,
            "bot_id": bot.id,
            "created_at": integration.created_at,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 2. Verify API Token (for use in Zapier setup)
@router.get("/verify")
async def verify_zapier_token(
    api_token: str = Header(..., alias="X-API-Token"),
    db: Session = Depends(get_db),
):
    integration = db.query(ZapierIntegration).filter_by(api_token=api_token).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invalid API token"
        )

    # Verify user exists
    user = db.query(User).filter_by(id=integration.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Verify bot exists
    bot = db.query(ChatBots).filter_by(id=integration.bot_id, user_id=user.id).first()
    if not bot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bot not found"
        )

    return {
        "valid": True,
        "user_id": user.id,
        "bot_id": bot.id,
        "email": integration.email,
    }


# 3. Message Handling Endpoint
@router.post("/message")
async def handle_zapier_message(
    message: str = Form(..., alias="Body"),  # Zapier will send as form data
    api_token: str = Header(..., alias="X-API-Token"),
    # session_id: str = Form(...),  # Unique identifier for conversation session
    db: Session = Depends(get_db),
):
    # Verify token and get integration
    integration = db.query(ZapierIntegration).filter_by(api_token=api_token).first()
    if not integration:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API token"
        )

    # Get bot response (reusing your core logic)
    response = get_response_from_chatbot(
        data={
            "message": message,
            "bot_id": integration.bot_id,
            "token": api_token,  # Use session_id to maintain conversation context
        },
        platform="zapier",
        db=db,
    )

    return {"response": response}
