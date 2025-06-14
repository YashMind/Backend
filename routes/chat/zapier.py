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
from routes.chat.pinecone import get_response_from_faqs
from schemas.authSchema.authSchema import User
from schemas.chatSchema.integrationsSchema import ZapierMessageRequest
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


@router.post("/me")
async def create_zapier_integration(
    api_token: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        print("API token : ", api_token)

        integration= db.query(ZapierIntegration).filter(ZapierIntegration.api_token == api_token).first()
        
        # Verify user owns the bot
        bot = db.query(ChatBots).filter(ChatBots.token == api_token).first()
        if not bot:
            print("Bot not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bot not found or you don't have permission",
            )

        user = db.query(AuthUser).filter(AuthUser.id == bot.user_id).first()

        if not user:
            print("User not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        if integration:
            return {
            "api_token": api_token,
            "bot_id": bot.id,
            "bot_name":bot.chatbot_name,
            "created_at": integration.created_at,
        }

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
            "bot_name":bot.chatbot_name,
            "created_at": integration.created_at,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscribe")
async def subscribe_zapier_trigger_hook(
    request: Request,
    api_token: str = Query(...),
    db: Session = Depends(get_db),
):
    try:

        print("API token : ", api_token)
        if not api_token:
            print("API token not found")
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API token not found, Please connect to a account first")
        
        print("request: ",request)

        integration= db.query(ZapierIntegration).filter(ZapierIntegration.api_token == api_token).first()

        if not integration:
            print("Connection not found")
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found, Please connect to a account first")
        
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
        
        integration.subscribed= True
        request_body = await request.json()
        hook_url = request_body.get("hookUrl")
        integration.webhook_url= hook_url

        db.commit()

        return {
            "api_token": api_token,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/unsubscribe")
async def subscribe_zapier_trigger_hook(
    api_token: str = Query(...),
    db: Session = Depends(get_db),
):
    try:

        print("API token : ", api_token)
        if not api_token:
            print("API token not found")
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API token not found, Please connect to a account first")
        

        integration= db.query(ZapierIntegration).filter(ZapierIntegration.api_token == api_token).first()

        if not integration:
            print("Connection not found")
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found, Please connect to a account first")
        
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
        
        integration.subscribed= False
        integration.webhook_url= None

        db.commit()

        return {
            "api_token": api_token,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.get("/perform-list")
async def subscribe_zapier_trigger_hook(
    request: Request,
    api_token: str = Query(...),
):
    try:

        print("request", request)
        print("API token : ", api_token)
        if not api_token:
            print("API token not found")
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API token not found, Please connect to a account first")

        return[ {
            "name": "Yashraa",
            "email": "admin@yashraa.ai",
            "contact": "9855555555",
            "message": "This is sample message for yashraa bot.",
            "type": "Lead",
        }]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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


@router.post("/message")
async def handle_zapier_message(
    body: ZapierMessageRequest,
    api_token: str = Header(..., alias="X-API-Token"),
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
            "message": body.message,
            "bot_id": integration.bot_id,
            "token": api_token,
        },
        platform="zapier",
        db=db,
    )

    return {"response": response}

