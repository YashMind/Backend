import secrets
import string
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from requests import Session

from config import get_db
from decorators.product_status import check_product_status
from models.chatModel.appearance import ChatSettings
from models.chatModel.chatModel import  ChatBots, ChatBotsDocLinks, ChatBotsFaqs, ChatMessage, ChatSession

from models.chatModel.integrations import WhatsAppUser, ZapierIntegration
from models.chatModel.sharing import ChatBotSharing
from models.chatModel.tuning import DBInstructionPrompt
from models.subscriptions.token_usage import TokenUsage, TokenUsageHistory
from routes.chat.chat import check_available_char_limit, has_chabot_limit
from routes.chat.pinecone import delete_documents_from_pinecone
from routes.chat.tuning import seed_instruction_prompts_template
from routes.subscriptions.token_usage import generate_token_usage
from schemas.chatSchema.chatSchema import  CreateBot
from utils.utils import decode_access_token


router = APIRouter()

# create new chatbot
@router.post("/create-bot", response_model=CreateBot)
@check_product_status("chatbot")
async def create_chatbot(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
        data = payload.get("data")
        token = request.cookies.get("access_token")
        decoded = decode_access_token(token)
        user_id = int(decoded.get("user_id"))
        generated_token = "".join(
            secrets.choice(string.ascii_lowercase + string.digits) for _ in range(25)
        )

        if not has_chabot_limit(user_id=user_id, db=db):
            raise HTTPException(
                status_code=400, detail="User has reached chatbot limit"
            )

        new_chatbot = ChatBots(
            user_id=user_id,
            chatbot_name=data.get("chatbot_name"),
            public=data.get("public"),
            train_from=data.get("train_from"),
            target_link=data.get("target_link"),
            document_link=data.get("document_link"),
            creativity=0,
            token=generated_token,
        )
        db.add(new_chatbot)
        db.flush()

        token_usage, message = generate_token_usage(
            bot_id=new_chatbot.id, user_id=new_chatbot.user_id, db=db
        )

        if not token_usage:
            raise HTTPException(status_code=404, detail=message)

        instruction_prompts, message = seed_instruction_prompts_template(
            user_id=user_id, bot_id=new_chatbot.id, domain=data.get("domain", ""), db=db
        )

        if not instruction_prompts:
            raise HTTPException(status_code=404, detail=message)

        db.commit()
        db.refresh(new_chatbot)

        return new_chatbot

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# update chatbot
@router.put("/update-bot", response_model=CreateBot)
@check_product_status("chatbot")
async def update_chatbot(data: CreateBot, db: Session = Depends(get_db)):
    try:
        chatbot = db.query(ChatBots).filter(ChatBots.id == int(data.id)).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="Chatbot not found")
        
        
        if data.train_from is not None:
            chatbot.train_from = data.train_from

        if data.target_link is not None:
            chatbot.target_link = data.target_link

        if data.document_link is not None:
            chatbot.document_link = data.document_link

        if data.text_content is not None:
            await check_available_char_limit(
                user_id=chatbot.user_id,
                db=db,
                new_chars=len(data.text_content),
            )
            chatbot.text_content = data.text_content

        if data.creativity is not None:
            chatbot.creativity = data.creativity

        if data.chatbot_name is not None:
            chatbot.chatbot_name = data.chatbot_name

        if data.public is not None:
            chatbot.public = data.public

        # ✅ Security fields
        if data.allow_domains is not None:
            chatbot.allow_domains = data.allow_domains

        if data.domains is not None:
            chatbot.domains = data.domains

        if data.rate_limit_enabled is not None:
            chatbot.rate_limit_enabled = data.rate_limit_enabled

        if data.limit_to is not None:
            chatbot.limit_to = data.limit_to

        if data.every_minutes is not None:
            chatbot.every_minutes = data.every_minutes

        # Save all updates
        db.commit()
        db.refresh(chatbot)

        return chatbot

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating chatbot: {str(e)}")


# get chatbot
@router.get("/get-bot", response_model=CreateBot)
@check_product_status("chatbot")
async def get_chatbot(botId: int, request: Request, db: Session = Depends(get_db)):
    try:

        chatbot = db.query(ChatBots).filter(ChatBots.id == botId).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="Chatbot not found")

        # If chatbot is public, allow access
        if chatbot.public:
            return chatbot

        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Check if user is the owner
        if chatbot.user_id == user_id:
            return chatbot

        # Check if chatbot is shared with the user
        sharing = (
            db.query(ChatBotSharing)
            .filter(
                ChatBotSharing.bot_id == botId,
                ChatBotSharing.shared_user_id == user_id,
                ChatBotSharing.status == "active",
            )
            .first()
        )

        if sharing:
            return chatbot

        raise HTTPException(
            status_code=403, detail="You don't have access to this chatbot"
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e), error=e)


@router.delete("/delete-bot/{bot_id}")
@check_product_status("chatbot")
async def delete_chatbot(bot_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Delete in correct order if not using ON DELETE CASCADE
        db.query(ChatBotsFaqs).filter(ChatBotsFaqs.bot_id == bot_id).delete(
            synchronize_session=False
        )

        docs_to_delete = (
            db.query(ChatBotsDocLinks)
            .filter(
                ChatBotsDocLinks.bot_id == bot_id,
            )
            .all()
        )

        if not docs_to_delete:
            print({"message": "No documents found to delete"})

        # Get the source links for Pinecone deletion
        doc_link_ids = [doc.id for doc in docs_to_delete]

        # Delete from Pinecone first
        delete_documents_from_pinecone(bot_id, doc_link_ids, db)

        db.query(ChatBotsDocLinks).filter(ChatBotsDocLinks.bot_id == bot_id).delete(
            synchronize_session=False
        )
        db.query(TokenUsage).filter(TokenUsage.bot_id == bot_id).delete(
            synchronize_session=False
        )
        db.query(TokenUsageHistory).filter(TokenUsageHistory.bot_id == bot_id).delete(
            synchronize_session=False
        )
        db.query(DBInstructionPrompt).filter(
            DBInstructionPrompt.bot_id == bot_id
        ).delete(synchronize_session=False)

        db.query(ChatSettings).filter(ChatSettings.bot_id == bot_id).delete(
            synchronize_session=False
        )

        # Get list of session IDs (flat list of values)
        session_ids = (
            db.query(ChatSession.id).filter(ChatSession.bot_id == bot_id).all()
        )
        session_ids = [s[0] for s in session_ids]  # unpack tuples

        if session_ids:
            db.query(ChatMessage).filter(ChatMessage.chat_id.in_(session_ids)).delete(
                synchronize_session=False
            )

        db.query(ChatSession).filter(ChatSession.bot_id == bot_id).delete(
            synchronize_session=False
        )

        db.query(ZapierIntegration).filter(ZapierIntegration.bot_id == bot_id).delete(
            synchronize_session=False
        )
        db.query(WhatsAppUser).filter(WhatsAppUser.bot_id == bot_id).delete(
            synchronize_session=False
        )
        db.query(ChatBotSharing).filter(ChatBotSharing.bot_id == bot_id).delete(
            synchronize_session=False
        )
        db.query(ChatBots).filter(
            ChatBots.id == bot_id, ChatBots.user_id == user_id
        ).delete(synchronize_session=False)
        db.commit()
        return {"message": "Chatbot with all data deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

