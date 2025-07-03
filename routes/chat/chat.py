from types import SimpleNamespace
from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    File,
    Query,
    BackgroundTasks,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
import httpx
import tiktoken
from models.adminModel.toolsModal import ToolsUsed
from models.chatModel.integrations import WhatsAppUser, ZapierIntegration
from models.subscriptions.token_usage import TokenUsage, TokenUsageHistory
from models.subscriptions.userCredits import UserCredits
from routes.chat.tuning import seed_instruction_prompts_template
from routes.subscriptions.token_usage import (
    generate_token_usage,
    update_token_usage_on_consumption,
    verify_token_limit_available,
)
from schemas.chatSchema.tokensSchema import (
    ChatMessageTokens,
    ChatMessageTokensSummary,
    ChatMessageTokensToday,
)
from utils.utils import decode_access_token, get_current_user
from uuid import uuid4
from sqlalchemy import or_, desc, asc
import json
from models.chatModel.chatModel import (
    ChatSession,
    ChatMessage,
    ChatBots,
    ChatBotsFaqs,
    ChatBotsDocLinks,
    ChatBotsDocChunks,
    ChatBotLeadsModel,
    ChatTotalToken,
)
from models.chatModel.sharing import ChatBotSharing
from schemas.chatSchema.chatSchema import (
    ChatMessageRead,
    ChatSessionRead,
    ChatSessionWithMessages,
    CreateBot,
    DeleteChatsRequest,
    CreateBotFaqs,
    FaqResponse,
    CreateBotDocLinks,
    DeleteDocLinksRequest,
    ChatbotLeads,
    DeleteChatbotLeadsRequest,
)
from schemas.chatSchema.sharingSchema import (
    DirectSharingRequest,
    EmailInviteRequest,
    BulkEmailInviteRequest,
    AcceptInviteRequest,
    SharingResponse,
    InviteResponse,
    AcceptInviteResponse,
)
from models.chatModel.appearance import ChatSettings
from models.chatModel.tuning import DBInstructionPrompt
from sqlalchemy.orm import Session
from config import get_db, settings
from typing import Optional, List
from collections import defaultdict
import os
from routes.chat.pinecone import (
    get_response_from_faqs,
    hybrid_retrieval,
    generate_response,
    delete_documents_from_pinecone,
)
from sqlalchemy import func, and_
from routes.chat.celery_worker import process_document_task
from decorators.product_status import check_product_status
import secrets
import string
from datetime import datetime, time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from models.authModel.authModel import AuthUser


router = APIRouter()


def generate_invite_token():
    """Generate a random token for invitation links"""
    return "".join(
        secrets.choice(string.ascii_letters + string.digits) for _ in range(32)
    )


async def send_invitation_email(
    recipient_email: str, invite_token: str, chatbot_name: str, owner_name: str
):
    """Send invitation email to the recipient"""
    try:
        # Create message
        message = MIMEMultipart()
        message["From"] = settings.EMAIL_ADDRESS
        message["To"] = recipient_email
        message["Subject"] = (
            f"You've been invited to collaborate on a chatbot: {chatbot_name}"
        )

        # Create the invite URL
        invite_url = f"{settings.FRONTEND_URL}/accept-invite/{invite_token}"

        # HTML content
        html = f"""
        <html>
        <body>
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2>Chatbot Invitation</h2>
                <p>Hello,</p>
                <p>{owner_name} has invited you to collaborate on the chatbot: <strong>{chatbot_name}</strong>.</p>
                <p>Click the button below to accept this invitation:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{invite_url}" style="background-color: #4CAF50; color: white; padding: 12px 20px; text-decoration: none; border-radius: 4px; font-weight: bold;">
                        Accept Invitation
                    </a>
                </div>
                <p>Or copy and paste this link in your browser:</p>
                <p>{invite_url}</p>
                <p>This invitation link will expire in 7 days.</p>
                <p>Thank you,<br>YashMind AI Team</p>
            </div>
        </body>
        </html>
        """

        # Attach HTML content
        message.attach(MIMEText(html, "html"))

        # Connect to SMTP server and send email
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
            server.send_message(message)

        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def has_chabot_limit(user_id: str, db: Session):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if not user:
            raise HTTPException("User not found")

        user_credits = (
            db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
        )
        if not user_credits:
            raise HTTPException("User credits not found")

        chatbots = db.query(ChatBots).filter(ChatBots.user_id == user_id).count()
        print("Chatbots allowed: ", chatbots, " limit: ", user_credits.chatbots_allowed)
        if chatbots >= user_credits.chatbots_allowed:
            return False

        return True

    except Exception as e:
        print(f"Error checking chatbot limit: {e}")
        return False, e


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
            user_id=user_id, bot_id=new_chatbot.id, db=db
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

        if data.train_from:
            chatbot.train_from = data.train_from

        if data.target_link:
            chatbot.target_link = data.target_link

        if data.document_link:
            chatbot.document_link = data.document_link

        if data.text_content:
            chatbot.text_content = data.text_content

        if data.creativity:
            chatbot.creativity = data.creativity

        if data.chatbot_name:
            chatbot.chatbot_name = data.chatbot_name

        if data.public is not None:
            chatbot.public = data.public

        if data.domains:
            chatbot.domains = data.domains
        if data.limit_to:
            chatbot.limit_to = data.limit_to
        if data.every_minutes:
            chatbot.every_minutes = data.every_minutes

        db.commit()
        db.refresh(chatbot)
        return chatbot

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

        db.query(ChatBots).filter(
            ChatBots.id == bot_id, ChatBots.user_id == user_id
        ).delete(synchronize_session=False)
        db.commit()
        return {"message": "Chatbot with all data deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


UPLOAD_DIRECTORY = "uploads/"
ALLOWED_FILE_TYPES = [
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "image/jpeg",
    "image/png",
    "image/webp",
    # Audio formats
    "audio/mpeg",  # .mp3
    "audio/wav",  # .wav
    "audio/x-wav",  # alternative .wav
    "audio/webm",  # .webm audio
    "audio/ogg",  # .ogg
    "audio/mp4",  # .m4a, .mp4 audio
    "audio/x-m4a",  # alternative .m4a
]


@router.post("/upload-document")
# @check_product_status("chatbot")
async def upload_photo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        # Validate file type
        if not os.path.exists(UPLOAD_DIRECTORY):
            os.makedirs(UPLOAD_DIRECTORY)

        if file.content_type not in ALLOWED_FILE_TYPES:
            raise HTTPException(
                status_code=400,
                detail="Invalid file type. Only image files are allowed.",
            )

        # Generate unique file name
        file_extension = file.filename.split(".")[-1]
        unique_filename = f"{uuid4()}.{file_extension}"
        file_path = os.path.join(UPLOAD_DIRECTORY, unique_filename)

        # Save the file
        try:
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
        except Exception as e:
            raise HTTPException(status_code=500, detail="Error saving file") from e

        file_url = f"/{UPLOAD_DIRECTORY}{unique_filename}"

        return JSONResponse(content={"url": file_url})

    except HTTPException as http_exc:
        raise http_exc

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/get-all")
@check_product_status("chatbot")
async def get_my_bots(
    request: Request, db: Session = Depends(get_db), include_shared: bool = Query(True)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Get user's own bots
        owned_bots = (
            db.query(ChatBots)
            .filter(ChatBots.user_id == user_id)
            .order_by(ChatBots.created_at.desc())
            .all()
        )

        user_credits = (
            db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
        )
        if user_credits is None:
            raise HTTPException(status_code=404, detail="User credits not found")

        if user_credits.chatbots_allowed < len(owned_bots):
            owned_bots = owned_bots[: user_credits.chatbots_allowed]

        # Get shared bots if include_shared is True
        shared_bots = []
        if include_shared:
            # Get IDs of bots shared with the user
            shared_bot_ids = (
                db.query(ChatBotSharing.bot_id)
                .filter(
                    ChatBotSharing.shared_user_id == user_id,
                    ChatBotSharing.status == "active",
                )
                .all()
            )
            shared_bot_ids = [bot_id for (bot_id,) in shared_bot_ids]

            if shared_bot_ids:
                shared_bots = (
                    db.query(ChatBots).filter(ChatBots.id.in_(shared_bot_ids)).all()
                )

        # Combine all bot IDs (owned + shared)
        all_bot_ids = [bot.id for bot in owned_bots] + [bot.id for bot in shared_bots]

        # Query chatbot settings for all bots at once if there are any
        if all_bot_ids:
            chatbot_settings = (
                db.query(ChatSettings)
                .filter(ChatSettings.bot_id.in_(all_bot_ids))
                .all()
            )
            settings_dict = {setting.bot_id: setting for setting in chatbot_settings}
        else:
            settings_dict = {}

        # Attach images to owned bots
        for bot in owned_bots:
            bot.image = (
                settings_dict.get(bot.id).image if settings_dict.get(bot.id) else None
            )

        # Attach images to shared bots
        for bot in shared_bots:
            bot.image = (
                settings_dict.get(bot.id).image if settings_dict.get(bot.id) else None
            )

        return owned_bots + shared_bots

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# create new chat
@router.post("/chats-id", response_model=ChatSessionRead)
@check_product_status("chatbot")
async def create_chat(
    data: ChatSessionRead, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        bot_id = data.bot_id
        last_chat = (
            db.query(ChatSession)
            .filter(ChatSession.user_id == user_id, ChatSession.bot_id == bot_id)
            .order_by(ChatSession.created_at.desc())
            .first()
        )

        # Step 2: Check if it has any messages
        if last_chat:
            has_messages = db.query(ChatMessage).filter_by(chat_id=last_chat.id).first()
            if not has_messages:
                return last_chat

        new_chat = ChatSession(user_id=user_id, bot_id=bot_id)
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        return new_chat

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chats-id-token", response_model=ChatSessionRead)
@check_product_status("chatbot")
async def create_chat_token_session(
    data: ChatSessionRead, request: Request, db: Session = Depends(get_db)
):
    try:
        chat_bot = db.query(ChatBots).filter_by(token=data.token).first()
        if not chat_bot:
            raise HTTPException(
                status_code=404, detail="ChatBot not found with given token"
            )
        if not chat_bot.public:
            # Step 2: Check if it has any messages
            token = request.cookies.get("access_token")
            if not token:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required for private chatbot",
                )
            payload = decode_access_token(token)
            user_id = int(payload.get("user_id"))
            existing_chat = (
                db.query(ChatSession)
                .filter_by(bot_id=chat_bot.id, user_id=user_id)
                .first()
            )
            if existing_chat:
                return existing_chat

            new_chat = ChatSession(
                token=data.token, bot_id=chat_bot.id, user_id=user_id
            )
            db.add(new_chat)
            db.commit()
            db.refresh(new_chat)
            return new_chat

        new_chat = ChatSession(token=data.token, bot_id=chat_bot.id)
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        return new_chat
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# send message
@router.post("/chats/{chat_id}/message", response_model=ChatMessageRead)
@check_product_status("chatbot")
async def chat_message(
    chat_id: int, data: dict, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        user_id = None
        if token:
            payload = decode_access_token(token)
            user_id = int(payload.get("user_id"))
        user_msg = data.get("message")
        bot_id = data.get("bot_id")
        if not user_msg:
            raise HTTPException(status_code=400, detail="Message required")

        chatbot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="ChatBot not found")

        token_limit_availabe, message = verify_token_limit_available(
            bot_id=bot_id, db=db
        )
        if not token_limit_availabe:
            raise HTTPException(
                status_code=400, detail=f"Token limit exceeded: {message}"
            )

        # Verify chat belongs to user
        chat = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        (
            request_tokens,
            response_tokens,
            openai_request_tokens,
            openai_response_tokens,
        ) = (0, 0, 0, 0)
        response_from_faqs = get_response_from_faqs(user_msg, bot_id, db)
        # # fallback to Pinecone if no FAQ match found
        # final_answer = response_from_faqs.answer if response_from_faqs else retrieve_answers(user_msg, bot_id)

        # # Set response_content
        # if final_answer:
        #     print("################# Got message from FAQ AND PINCONE ##################")
        #     response_content = final_answer
        # else:
        #     print("################# Sending message request to open ai ##################")
        #     # Get message history from DB
        #     messages = db.query(ChatMessage).filter_by(chat_id=chat_id).order_by(ChatMessage.created_at.asc()).all()
        #     langchain_messages = [
        #         HumanMessage(content=m.message) if m.sender == 'user' else AIMessage(content=m.message)
        #         for m in messages
        #     ]
        #     langchain_messages.append(HumanMessage(content=user_msg))
        #     response = llm.invoke(langchain_messages)
        #     response_content = response.content if response and response.content else "No response"

        response_content = response_from_faqs.answer if response_from_faqs else None

        active_tool = db.query(ToolsUsed).filter_by(status=True).first()
        if not response_content:
            print("No response found from FAQ")
            # Hybrid retrieval
            context_texts, scores = hybrid_retrieval(
                query=user_msg, bot_id=bot_id, db=db, tool=active_tool
            )

            instruction_prompts = (
                db.query(DBInstructionPrompt)
                .filter(DBInstructionPrompt.bot_id == bot_id)
                .all()
            )
            dict_ins_prompt = [
                {prompt.type: prompt.prompt} for prompt in instruction_prompts
            ]
            # print("DICT INSTRUCTION PROMPTS",dict_ins_prompt)

            creativity = chatbot.creativity
            text_content = chatbot.text_content

            answer = None
            print("Hybrid retrieval results: ", context_texts, scores)
            # Determine answer source

            # if any(score > 0.0 for score in scores):
            if len(scores) > 0:
                print("using openai with context")
                use_openai = True
                generated_res = generate_response(
                    user_msg,
                    context_texts[:3],
                    use_openai,
                    dict_ins_prompt,
                    creativity,
                    text_content,
                    active_tool=active_tool,
                )
                answer = generated_res[0]
                openai_request_tokens = generated_res[1]
                openai_response_tokens = generated_res[2]
                request_tokens = generated_res[3]
                print("ANSWER", answer, openai_request_tokens)

            else:
                print(
                    "no direct scores from hybrid retrieval and using openai independently"
                )
                # Full OpenAI fallback
                use_openai = True
                generated_res = generate_response(
                    user_msg,
                    [],
                    use_openai,
                    dict_ins_prompt,
                    creativity,
                    text_content,
                    active_tool=active_tool,
                )
                answer = generated_res[0]
                openai_request_tokens = generated_res[1]
                openai_response_tokens = generated_res[2]
                request_tokens = generated_res[3]
                print("ANSWER", answer, openai_request_tokens)

            response_content = answer

        # Save user and bot messages
        user_message = ChatMessage(
            user_id=user_id,
            bot_id=bot_id,
            chat_id=chat_id,
            sender="user",
            message=user_msg,
        )
        bot_message = ChatMessage(
            user_id=user_id,
            bot_id=bot_id,
            chat_id=chat_id,
            sender="bot",
            message=response_content,
        )

        db.add_all([user_message, bot_message])
        db.commit()
        db.refresh(bot_message)
        print("BOT MESSAGE SAVED")

        # Update Token consumption
        bot_message.input_tokens = request_tokens
        bot_message.output_tokens = openai_response_tokens
        bot_message.open_ai_request_tokens = openai_request_tokens
        bot_message.open_ai_response_tokens = openai_response_tokens

        consumed_token = SimpleNamespace(
            request_token=request_tokens,
            response_token=openai_response_tokens,
            open_ai_request_token=openai_request_tokens,
            open_ai_response_token=openai_response_tokens,
        )
        update_token_usage_on_consumption(
            consumed_token=consumed_token,
            consumed_token_type="direct_bot",
            bot_id=bot_id,
            db=db,
        )

        return bot_message
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# get all charts
@router.get("/chats", response_model=List[ChatSessionWithMessages])
@check_product_status("chatbot")
async def list_chats(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        chats = (
            db.query(ChatSession)
            .filter_by(user_id=user_id, archived=False)
            .order_by(ChatSession.created_at.desc())
            .all()
        )
        return chats
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# load chat history
@router.get("/chats/{chat_id}", response_model=List[ChatMessageRead])
@check_product_status("chatbot")
async def get_chat_history(
    chat_id: int, request: Request, db: Session = Depends(get_db)
):
    try:
        chat = db.query(ChatSession).filter_by(id=chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        messages = (
            db.query(ChatMessage)
            .filter_by(chat_id=chat_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        return messages
        # return [ChatMessageRead.from_orm(message) for message in messages]
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/chats-history/archived")
@check_product_status("chatbot")
async def get_user_chat_history(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    search: Optional[str] = None,
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        chat_bots = db.query(ChatBots).filter_by(user_id=user_id).all()
        response_data = []

        for chat_bot in chat_bots:
            # Query sessions for this specific chatbot
            session_query = db.query(ChatSession).filter_by(
                user_id=user_id, archived=True, bot_id=chat_bot.id
            )

            # Apply search filter
            if search:
                session_query = session_query.join(ChatMessage).filter(
                    ChatMessage.message.ilike(f"%{search}%")
                )

            # Get paginated results
            total_count = session_query.count()
            sessions = session_query.offset((page - 1) * limit).limit(limit).all()

            if not sessions:
                response_data.append(
                    {
                        "chatBotId": chat_bot.id,
                        "chatBotName": chat_bot.chatbot_name,
                        "sessions": [],
                        "totalCount": 0,
                        "totalPages": 0,
                        "currentPage": page,
                    }
                )
                continue

            # Get messages for these sessions
            session_ids = [int(s.id) for s in sessions]
            messages = (
                db.query(ChatMessage)
                .filter(ChatMessage.chat_id.in_(session_ids))
                .order_by(ChatMessage.created_at.asc())
                .all()
            )

            # Group messages
            grouped_messages = defaultdict(list)
            for message in messages:
                grouped_messages[message.chat_id].append(message)

            # Convert to dict and sort
            sorted_grouped = dict(
                sorted(grouped_messages.items(), key=lambda x: x[0], reverse=True)
            )

            response_data.append(
                {
                    "chatBotId": chat_bot.id,
                    "chatBotName": chat_bot.chatbot_name,
                    "sessions": sorted_grouped,
                    "totalCount": total_count,
                    "totalPages": (total_count + limit - 1) // limit,
                    "currentPage": page,
                }
            )

        return {
            "data": jsonable_encoder(response_data),
            "globalTotal": sum(item["totalCount"] for item in response_data),
            "globalPages": (
                sum(item["totalCount"] for item in response_data) + limit - 1
            )
            // limit,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error fetching chat history: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


# get user chat history
@router.get("/chats-history/{bot_id}")
@check_product_status("chatbot")
async def get_user_chat_history(
    bot_id: int,
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1),
    search: Optional[str] = None,
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        chat_bot = db.query(ChatBots).filter_by(id=bot_id, user_id=user_id).first()
        session_query = db.query(ChatSession).filter_by(bot_id=bot_id, archived=False)
        if not session_query:
            raise HTTPException(status_code=404, detail="Chat not found")
        if search:
            session_query = session_query.filter(
                ChatMessage.message.ilike(f"%{search}%")
            )

        total_count = session_query.count()
        # Apply pagination
        sessions = session_query.offset((page - 1) * limit).limit(limit).all()
        session_ids = [s.id for s in sessions]
        if not session_ids:
            return {
                "data": {},
                "totalCount": total_count,
                "totalPages": (total_count + limit - 1) // limit,
                "currentPage": page,
                "chatBot": chat_bot,
            }

        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.chat_id.in_(session_ids))
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        # Build a map of session_id to session (to get platform)
        session_map = {session.id: session for session in sessions}

        # Group messages by chat_id and include platform
        grouped_sessions = {}
        for message in messages:
            chat_id = message.chat_id
            if chat_id not in grouped_sessions:
                grouped_sessions[chat_id] = {
                    "platform": session_map[chat_id].platform,
                    "messages": [],
                }
            grouped_sessions[chat_id]["messages"].append(message)

        # Optional: sort by chat_id descending
        sorted_grouped = dict(
            sorted(grouped_sessions.items(), key=lambda x: x[0], reverse=True)
        )

        return {
            "data": sorted_grouped,
            "totalCount": total_count,
            "totalPages": (total_count + limit - 1) // limit,
            "currentPage": page,
            "chatBot": chat_bot,
        }
        # return sorted_grouped
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e))  # get user chat history


@router.delete("/delete-chats/{bot_id}")
@check_product_status("chatbot")
async def delete_chat(
    bot_id: int,
    request_data: DeleteChatsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        for chat_id in request_data.chat_ids:
            chat = (
                db.query(ChatSession)
                .filter_by(id=chat_id, user_id=user_id, bot_id=bot_id)
                .first()
            )
            if chat:
                db.query(ChatMessage).filter_by(chat_id=chat_id).delete()
                db.delete(chat)
        db.commit()
        return {"message": "Chat deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chats")
@check_product_status("chatbot")
async def delete_all_chats_by_user(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        user_chats = db.query(ChatSession).filter_by(user_id=user_id).all()
        for chat in user_chats:
            db.query(ChatMessage).filter_by(chat_id=chat.id).delete()
            db.delete(chat)

        db.commit()
        return {"message": "All chats deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chats/delete-all")
@check_product_status("chatbot")
async def delete_all_chats_by_bots(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        user_bots = db.query(ChatBots).filter(ChatBots.user_id == user_id).all()
        for bot in user_bots:
            bot_chats = db.query(ChatSession).filter(ChatSession.bot_id == bot.id).all()
            for chat in bot_chats:
                db.query(ChatMessage).filter_by(chat_id=chat.id).delete()
                db.delete(chat)

        db.commit()
        return {"message": "All chats deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/chats/archive")
@check_product_status("chatbot")
async def archive_all_chats(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        user = db.query(AuthUser).filter(AuthUser.id == user_id).all()
        if not user:
            raise HTTPException(status_code=404, detail="user not found")

        chatbots = db.query(ChatBots).filter(ChatBots.user_id == user_id).all()
        if not chatbots:
            raise HTTPException(status=400, detail="No chatbot found")

        for bot in chatbots:
            user_chats = (
                db.query(ChatSession).filter(ChatSession.bot_id == bot.id).all()
            )
            for chat in user_chats:
                chat.archived = True

        db.commit()

        return {"message": "All chats archived successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# create new chatbot
@router.post("/create-bot-faqs", response_model=CreateBotFaqs)
@check_product_status("chatbot")
async def create_chatbot_faqs(
    data: CreateBotFaqs, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        created_faqs = []

        for qa in data.questions:
            new_chatbot_faq = ChatBotsFaqs(
                user_id=user_id,
                bot_id=data.bot_id,
                question=qa.question,
                answer=qa.answer,
            )
            db.add(new_chatbot_faq)
            db.commit()
            db.refresh(new_chatbot_faq)
            created_faqs.append(new_chatbot_faq)
            # return new_chatbot_faq

        return {"bot_id": data.bot_id, "questions": created_faqs}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-bot-faqs/{bot_id}", response_model=List[FaqResponse])
@check_product_status("chatbot")
async def get_chatbot_faqs(
    bot_id: int, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        chatbot_faqs = (
            db.query(ChatBotsFaqs)
            .filter_by(bot_id=bot_id, user_id=user_id)
            .order_by(ChatBotsFaqs.created_at.desc())
            .all()
        )
        return chatbot_faqs

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-faq/{bot_id}/{faq_id}")
@check_product_status("chatbot")
async def delete_single_faq(
    bot_id: int, faq_id: int, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        faq = (
            db.query(ChatBotsFaqs)
            .filter_by(id=faq_id, bot_id=bot_id, user_id=user_id)
            .first()
        )
        if not faq:
            raise HTTPException(status_code=404, detail="FAQ not found")

        db.delete(faq)
        db.commit()

        return {"message": "FAQ deleted successfully."}
    except Exception as e:
        print("Delete single FAQ error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-all-faqs/{bot_id}")
@check_product_status("chatbot")
async def delete_all_faqs(bot_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Delete all FAQ entries for the bot and user
        deleted = (
            db.query(ChatBotsFaqs).filter_by(bot_id=bot_id, user_id=user_id).delete()
        )
        db.commit()

        return {"message": f"{deleted} FAQs deleted successfully."}
    except Exception as e:
        print("Delete all FAQs error:", e)
        raise HTTPException(status_code=500, detail=str(e))


# create new chatbot doc
@router.post("/create-bot-doc-links", response_model=CreateBotDocLinks)
@check_product_status("chatbot")
async def create_chatbot_docs(
    data: CreateBotDocLinks, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        new_chatbot_doc_links = data
        new_chatbot_doc_links.user_id = user_id

        exsiting = None
        if data.target_link:
            exsiting = (
                db.query(ChatBotsDocLinks)
                .filter(
                    ChatBotsDocLinks.bot_id == int(data.bot_id),
                    ChatBotsDocLinks.target_link == data.target_link,
                )
                .first()
            )
        if data.document_link:
            exsiting = (
                db.query(ChatBotsDocLinks)
                .filter(
                    ChatBotsDocLinks.bot_id == int(data.bot_id),
                    ChatBotsDocLinks.document_link == data.document_link,
                )
                .first()
            )
        if exsiting and exsiting.train_from == data.train_from:
            raise HTTPException(
                status_code=400,
                detail=f"Target link already exists in {data.train_from} training.",
            )

        new_doc = ChatBotsDocLinks(
            user_id=user_id,
            bot_id=int(data.bot_id),
            chatbot_name=data.chatbot_name,
            train_from=data.train_from,
            target_link=data.target_link,
            document_link=data.document_link,
            public=data.public,
            status="pending",
            chars=0,
        )
        db.add(new_doc)
        db.commit()

        process_document_task.delay(new_doc.id)

        return new_doc

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Check doc status
@router.get("/document-status/{doc_id}")
@check_product_status("chatbot")
async def get_document_status(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(ChatBotsDocLinks).get(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": doc.status}


@router.get("/get-bot-doc-links/{bot_id}")
@check_product_status("chatbot")
async def get_bot_doc_links(
    bot_id: int,
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(
        None, description="Search by document_link or target_link"
    ),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(ChatBotsDocLinks).filter(
            ChatBotsDocLinks.user_id == user_id,
            ChatBotsDocLinks.bot_id == bot_id,
            ChatBotsDocLinks.train_from != "full website",
        )

        # Query to get all website links (train_from = "full website")
        website_links = (
            db.query(ChatBotsDocLinks)
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.train_from == "full website",
            )
            .all()
        )

        user_credit = (
            db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
        )

        # Group website links by parent_link_id
        website_groups = {}
        for link in website_links:
            parent_id = link.parent_link_id  # Use id if parent_link_id is None
            if parent_id not in website_groups:
                website_groups[parent_id] = []
            website_groups[parent_id].append(link)

        # Process each website group
        websites = []
        for parent_id, links in website_groups.items():
            # Find the main/parent link (where id == parent_link_id or where parent_link_id is None)
            parent_link = next(
                (link for link in links if link.id == parent_id), links[0]
            )

            # Calculate stats for this website group
            group_total_target_links = len(links)
            group_total_document_links = sum(1 for link in links if link.document_link)

            group_pending_count = sum(
                1
                for link in links
                if link.status == "Pending" or link.status == "training"
            )
            group_failed_count = sum(1 for link in links if link.status == "Failed")
            group_indexed_count = sum(1 for link in links if link.status == "Indexed")

            group_total_chars = sum(link.chars or 0 for link in links)

            websites.append(
                {
                    "source": parent_link.target_link,  # The main website URL
                    "link": links,
                    "total_target_links": group_total_target_links,
                    "total_document_links": group_total_document_links,
                    "pending_count": group_pending_count,
                    "failed_count": group_failed_count,
                    "indexed_count": group_indexed_count,
                    "total_chars": group_total_chars,
                }
            )
        total_target_links = (
            db.query(ChatBotsDocLinks)
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.train_from != "full website",
                and_(
                    ChatBotsDocLinks.target_link.isnot(None),
                    ChatBotsDocLinks.target_link != "",
                ),
            )
            .count()
        )

        user_target_links = (
            db.query(ChatBotsDocLinks)
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                and_(
                    ChatBotsDocLinks.target_link.isnot(None),
                    ChatBotsDocLinks.target_link != "",
                ),
            )
            .count()
        )

        # Count where document_link is not null and not empty
        total_document_links = (
            db.query(ChatBotsDocLinks)
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.train_from != "full website",
                and_(
                    ChatBotsDocLinks.document_link.isnot(None),
                    ChatBotsDocLinks.document_link != "",
                ),
            )
            .count()
        )

        total_chars = (
            db.query(func.sum(ChatBotsDocLinks.chars))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.train_from
                != "full website",  # Exclude full website documents
            )
            .scalar()
            or 0
        )
        user_total_chars = (
            db.query(func.sum(ChatBotsDocLinks.chars))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
            )
            .scalar()
            or 0
        )
        pending_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                or_(
                    ChatBotsDocLinks.status == "Pending",
                    ChatBotsDocLinks.status == "training",
                ),
                ChatBotsDocLinks.train_from != "full website",
            )
            .scalar()
        )

        user_pending_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Pending",
            )
            .scalar()
        )

        failed_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Failed",
                ChatBotsDocLinks.train_from != "full website",
            )
            .scalar()
        )
        user_failed_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Failed",
            )
            .scalar()
        )

        indexed_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Indexed",
                ChatBotsDocLinks.train_from != "full website",
            )
            .scalar()
        )
        user_indexed_count = (
            db.query(func.count(ChatBotsDocLinks.id))
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Indexed",
            )
            .scalar()
        )

        # Apply search
        if search:
            query = query.filter(
                or_(
                    ChatBotsDocLinks.document_link.ilike(f"%{search}%"),
                    ChatBotsDocLinks.target_link.ilike(f"%{search}%"),
                )
            )

        # Sorting
        sort_column = getattr(ChatBotsDocLinks, sort_by, ChatBotsDocLinks.created_at)
        sort_column = desc(sort_column) if sort_order == "desc" else asc(sort_column)
        query = query.order_by(sort_column)

        # Pagination
        total_count = query.count()
        total_pages = (total_count + limit - 1) // limit
        results = query.offset((page - 1) * limit).limit(limit).all()

        return {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "data": [
                {
                    "source": "links",
                    "link": results,
                    "total_target_links": total_target_links,
                    "total_document_links": total_document_links,
                    "pending_count": pending_count,
                    "failed_count": failed_count,
                    "indexed_count": indexed_count,
                    "total_chars": (
                        total_chars
                        if total_chars <= user_credit.chars_allowed
                        else user_credit.chars_allowed
                    ),
                },
                *websites,
            ],
            "Indexed": 2,
            "user_target_links": user_target_links,
            "user_pending_count": user_pending_count,
            "user_failed_count": user_failed_count,
            "user_indexed_count": user_indexed_count,
            "user_total_chars": (
                user_total_chars
                if user_total_chars <= user_credit.chars_allowed
                else user_credit.chars_allowed
            ),
            "allowed_total_chars": (
                user_credit.chars_allowed
                if user_credit and user_credit.chars_allowed
                else 0
            ),
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-doc-links/{bot_id}")
@check_product_status("chatbot")
async def delete_doc_links(
    bot_id: int,
    request_data: DeleteDocLinksRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # First get all document links that will be deleted
        docs_to_delete = (
            db.query(ChatBotsDocLinks)
            .filter(
                ChatBotsDocLinks.id.in_(request_data.doc_ids),
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
            )
            .all()
        )

        if not docs_to_delete:
            return {"message": "No documents found to delete"}

        # Get the source links for Pinecone deletion
        doc_link_ids = [doc.id for doc in docs_to_delete]

        # Delete from Pinecone first
        deletion_stats = delete_documents_from_pinecone(bot_id, doc_link_ids, db)

        # # Clear whole pinecone
        # clear_all_pinecone_namespaces(db)

        # Then delete from database
        db.query(ChatBotsDocLinks).filter(
            ChatBotsDocLinks.id.in_(request_data.doc_ids),
            ChatBotsDocLinks.user_id == user_id,
            ChatBotsDocLinks.bot_id == bot_id,
        ).delete(synchronize_session=False)

        db.commit()

        return {
            "message": "Documents deleted successfully",
            "pinecone_deletion_stats": deletion_stats,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/chats-delete-token/{token}")
@check_product_status("chatbot")
async def delete_token_chat(token: str, db: Session = Depends(get_db)):
    try:
        chat_session = db.query(ChatSession).filter(ChatSession.token == token).first()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Chat session not found")

        # Delete all messages related to this chat
        db.query(ChatMessage).filter(ChatMessage.chat_id == chat_session.id).delete()

        db.commit()
        return {"message": "Chat deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/user-chats-delete/{chat_id}")
@check_product_status("chatbot")
async def delete_user_chats(chat_id: int, db: Session = Depends(get_db)):
    try:
        # Delete all messages related to this chat
        db.query(ChatMessage).filter(ChatMessage.chat_id == chat_id).delete()
        db.commit()
        return {"message": "Chat deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# create new chatbot
@router.post("/create-bot-leads", response_model=ChatbotLeads)
@check_product_status("chatbot")
async def create_chatbot_leads(
    data: ChatbotLeads, request: Request, db: Session = Depends(get_db)
):
    try:
        chatbot = db.query(ChatBots).filter(ChatBots.id == data.bot_id).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="Chatbot not found")

        user_id = None

        # Require auth if chatbot is NOT public
        if not chatbot.public:
            token = request.cookies.get("access_token")
            if not token:
                raise HTTPException(
                    status_code=401, detail="Unauthorized: Token missing"
                )

            payload = decode_access_token(token)
            if not payload or "user_id" not in payload:
                raise HTTPException(
                    status_code=401, detail="Unauthorized: Invalid token"
                )

            user_id = int(payload["user_id"])
        else:
            user_id = None

        new_chatbot_lead = ChatBotLeadsModel(
            user_id=user_id or None,
            bot_id=data.bot_id,
            chat_id=data.chat_id,
            name=data.name,
            email=data.email,
            contact=data.contact,
            message=data.message,
            type=data.type,
        )
        db.add(new_chatbot_lead)
        db.commit()
        db.refresh(new_chatbot_lead)

        # Fetch zapier webhook details
        zapier_webhook = (
            db.query(ZapierIntegration)
            .filter(ZapierIntegration.api_token == chatbot.token)
            .first()
        )

        if zapier_webhook and zapier_webhook.subscribed:
            webhook_data = [
                {
                    "name": new_chatbot_lead.name,
                    "email": new_chatbot_lead.email,
                    "contact": new_chatbot_lead.contact,
                    "message": new_chatbot_lead.message,
                    "type": new_chatbot_lead.type,
                }
            ]
            try:
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(
                        zapier_webhook.webhook_url, json=webhook_data
                    )
                    print(
                        "Zapier webhook response:", response.status_code, response.text
                    )
            except httpx.HTTPError as e:
                print("Error sending data to Zapier webhook:", str(e))

        return new_chatbot_lead

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-chatbot-leads/{bot_id}")
@check_product_status("chatbot")
async def get_chatbot_leads(
    bot_id: int,
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(
        None, description="Search by document_link or target_link"
    ),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(ChatBotLeadsModel).filter(ChatBotLeadsModel.bot_id == bot_id)

        # Apply search
        if search:
            query = query.filter(
                or_(
                    ChatBotLeadsModel.name.ilike(f"%{search}%"),
                    ChatBotLeadsModel.email.ilike(f"%{search}%"),
                )
            )

        # Sorting
        sort_column = getattr(ChatBotLeadsModel, sort_by, ChatBotLeadsModel.created_at)
        sort_column = desc(sort_column) if sort_order == "desc" else asc(sort_column)
        query = query.order_by(sort_column)

        # Pagination
        total_count = query.count()
        total_pages = (total_count + limit - 1) // limit
        results = query.offset((page - 1) * limit).limit(limit).all()

        return {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "data": results,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-chatbot-leads/{bot_id}")
@check_product_status("chatbot")
async def delete_doc_links(
    bot_id: int,
    request_data: DeleteChatbotLeadsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        for lead_id in request_data.lead_ids:
            doc = (
                db.query(ChatBotLeadsModel)
                .filter_by(id=lead_id, user_id=user_id, bot_id=bot_id)
                .first()
            )
            if doc:
                db.delete(doc)
        db.commit()
        return {"message": "Chatbot leads deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leads/{chat_id}/messages", response_model=List[ChatMessageRead])
@check_product_status("chatbot")
async def chat_lead_messages(
    chat_id: int, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.created_at.asc())
            .all()
        )
        print("messages ", messages)
        return messages
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tokens", response_model=ChatMessageTokens)
@check_product_status("chatbot")
async def chat_message_tokens(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        if not token:
            print("Access token missing from cookies.")
            raise HTTPException(status_code=401, detail="Access token missing")

        payload = decode_access_token(token)
        user_id = payload.get("user_id")

        if user_id is None:
            print("User ID missing in decoded token payload:", payload)
            raise HTTPException(status_code=401, detail="Invalid access token")

        user_id = int(user_id)
        print(f"Decoded user_id: {user_id}")

        credits = db.query(UserCredits).filter_by(user_id=user_id).first()
        print(f"Fetched credits: {credits}")
        if not credits:
            print("User credits not found")
            raise HTTPException(status_code=404, detail="No Credit History Found")

        token_usages = db.query(TokenUsage).filter_by(user_id=user_id).all()
        print(f"Fetched {len(token_usages)} token usage records")

        total_token_consumption = sum(
            usage.combined_token_consumption or 0 for usage in token_usages
        )
        print(f"Total token consumption: {total_token_consumption}")

        return ChatMessageTokens(
            credits=credits,
            token_usage=token_usages,
            total_token_consumption=total_token_consumption,
        )

    except HTTPException as http_exc:
        print(f"HTTPException: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        print("Unhandled exception in /tokens endpoint:", str(e))
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/tokens/{bot_id}/summary", response_model=ChatMessageTokensSummary)
async def chat_message_tokens_summary(
    request: Request, bot_id: int, db: Session = Depends(get_db)
):
    try:
        # Get current date and time
        now = datetime.now()
        today = now.date()

        # Calculate date ranges
        start_of_day = datetime.combine(today, time.min)
        end_of_day = datetime.combine(today, time.max)

        # First day of current month
        start_of_month = datetime(today.year, today.month, 1)

        # Initialize encoder
        encoder = tiktoken.encoding_for_model("gpt-3.5-turbo")

        # Helper function to process messages and calculate tokens
        def process_messages(messages):
            user_messages = []
            bot_messages = []
            user_ids = set()

            for message in messages:
                if message.sender == "user":
                    user_messages.append(message.message)
                    user_ids.add(message.user_id)
                elif message.sender == "bot":
                    bot_messages.append(message.message)

            # Calculate tokens
            request_tokens = 0
            if user_messages:
                combined_user_text = " ".join(user_messages)
                request_tokens = len(encoder.encode(combined_user_text))

            response_tokens = 0
            if bot_messages:
                combined_bot_text = " ".join(bot_messages)
                response_tokens = len(encoder.encode(combined_bot_text))

            return {
                "request_tokens": request_tokens,
                "response_tokens": response_tokens,
                "users": len(user_ids),
            }

        # Get today's messages
        today_messages = (
            db.query(ChatMessage)
            .filter(
                and_(
                    ChatMessage.bot_id == bot_id,
                    ChatMessage.created_at >= start_of_day,
                    ChatMessage.created_at <= end_of_day,
                )
            )
            .all()
        )

        # Get monthly messages
        monthly_messages = (
            db.query(ChatMessage)
            .filter(
                and_(
                    ChatMessage.bot_id == bot_id,
                    ChatMessage.created_at >= start_of_month,
                    ChatMessage.created_at <= end_of_day,
                )
            )
            .all()
        )

        # Process both time periods
        today_data = (
            process_messages(today_messages)
            if today_messages
            else {"request_tokens": 0, "response_tokens": 0, "users": 0}
        )

        monthly_data = (
            process_messages(monthly_messages)
            if monthly_messages
            else {"request_tokens": 0, "response_tokens": 0, "users": 0}
        )

        return {"today": today_data, "monthly": monthly_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/invite-users", response_model=InviteResponse)
@check_product_status("chatbot")
async def invite_users(
    data: BulkEmailInviteRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """Invite multiple users to a chatbot via email"""
    try:
        # Get current user from token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = decode_access_token(token)
        owner_id = int(payload.get("user_id"))
        owner_name = payload.get("username", "A user")

        # Check if chatbot exists and user is the owner
        chatbot = (
            db.query(ChatBots)
            .filter(ChatBots.id == data.bot_id, ChatBots.user_id == owner_id)
            .first()
        )

        if not chatbot:
            raise HTTPException(
                status_code=404, detail="Chatbot not found or you don't have permission"
            )

        # Process each email
        invites = []
        for email in data.user_emails:
            # Check if user with this email exists
            user = db.query(AuthUser).filter(AuthUser.email == email).first()

            # Check if sharing already exists
            existing_share = None
            if user:
                existing_share = (
                    db.query(ChatBotSharing)
                    .filter(
                        ChatBotSharing.bot_id == data.bot_id,
                        ChatBotSharing.shared_user_id == user.id,
                    )
                    .first()
                )
            else:
                existing_share = (
                    db.query(ChatBotSharing)
                    .filter(
                        ChatBotSharing.bot_id == data.bot_id,
                        ChatBotSharing.shared_email == email,
                    )
                    .first()
                )

            if existing_share and existing_share.status == "active":
                # Skip if already shared
                continue
            elif existing_share and existing_share.status == "pending":
                # Update existing pending invitation
                invite_token = generate_invite_token()
                existing_share.invite_token = invite_token
                existing_share.updated_at = datetime.now()
                db.commit()
                db.refresh(existing_share)
                invites.append(existing_share)

                # Send invitation email
                background_tasks.add_task(
                    send_invitation_email,
                    email,
                    invite_token,
                    chatbot.chatbot_name,
                    owner_name,
                )
            else:
                # Create new sharing record
                invite_token = generate_invite_token()
                new_sharing = ChatBotSharing(
                    bot_id=data.bot_id,
                    owner_id=owner_id,
                    shared_email=email,
                    shared_user_id=user.id if user else None,
                    invite_token=invite_token,
                    status="pending",
                )

                db.add(new_sharing)
                db.commit()
                db.refresh(new_sharing)
                invites.append(new_sharing)

                # Send invitation email
                background_tasks.add_task(
                    send_invitation_email,
                    email,
                    invite_token,
                    chatbot.chatbot_name,
                    owner_name,
                )

        return {
            "message": f"Invitations sent to {len(invites)} users",
            "invites": invites,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/accept-invite/{token}", response_model=AcceptInviteResponse)
async def accept_invite(token: str, request: Request, db: Session = Depends(get_db)):
    """Accept an invitation using the token"""
    try:
        # Get current user from token
        auth_token = request.cookies.get("access_token")
        if not auth_token:
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = decode_access_token(auth_token)
        user_id = int(payload.get("user_id"))
        user_email = payload.get("sub")  # Email is stored in 'sub' claim

        # Find the invitation
        invitation = (
            db.query(ChatBotSharing)
            .filter(
                ChatBotSharing.invite_token == token, ChatBotSharing.status == "pending"
            )
            .first()
        )

        if not invitation:
            raise HTTPException(status_code=404, detail="Invalid or expired invitation")

        # Check if the invitation matches the current user's email
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if invitation.shared_email and invitation.shared_email != user.email:
            raise HTTPException(
                status_code=403,
                detail="This invitation was sent to a different email address",
            )

        # Update the invitation
        invitation.shared_user_id = user_id
        invitation.status = "active"
        invitation.updated_at = datetime.now()

        db.commit()
        db.refresh(invitation)

        return {"message": "Invitation accepted successfully", "sharing": invitation}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/shared-chatbots", response_model=List[SharingResponse])
async def get_shared_chatbots(request: Request, db: Session = Depends(get_db)):
    """Get all chatbots shared with the current user"""
    try:
        # Get current user from token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Find all active sharing records for this user
        shared_chatbots = (
            db.query(ChatBotSharing)
            .filter(
                ChatBotSharing.shared_user_id == user_id,
                ChatBotSharing.status == "active",
            )
            .all()
        )

        return shared_chatbots

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/revoke-sharing/{sharing_id}", response_model=SharingResponse)
async def revoke_sharing(
    sharing_id: int, request: Request, db: Session = Depends(get_db)
):
    """Revoke a sharing by its ID"""
    try:
        # Get current user from token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Find the sharing record
        sharing = (
            db.query(ChatBotSharing).filter(ChatBotSharing.id == sharing_id).first()
        )

        if not sharing:
            raise HTTPException(status_code=404, detail="Sharing record not found")

        # Check if the current user is the owner
        if sharing.owner_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to revoke this sharing",
            )

        # Update the status to revoked
        sharing.status = "revoked"
        sharing.updated_at = datetime.now()

        db.commit()
        db.refresh(sharing)

        return sharing

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
