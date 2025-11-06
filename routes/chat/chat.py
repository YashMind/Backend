import re
from types import SimpleNamespace
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    UploadFile,
    File,
    Query,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
import tiktoken
from models.adminModel.toolsModal import ToolsUsed
from models.chatModel.integrations import WhatsAppUser, ZapierIntegration
from models.subscriptions.token_usage import TokenUsage, TokenUsageHistory
from models.subscriptions.userCredits import UserCredits
from routes.chat.tuning import seed_instruction_prompts_template
from routes.subscriptions.token_usage import (
    check_rate_limit,
    generate_token_usage,
    update_token_usage_on_consumption,
    verify_token_limit_available,
)
from schemas.chatSchema.tokensSchema import (
    ChatMessageTokensSummary,
)
from utils.utils import (
    decode_access_token,
    get_recent_chat_history,
    validate_response,
    handle_invalid_response,
)
from uuid import uuid4
import json
from models.chatModel.chatModel import (
    ChatSession,
    ChatMessage,
    ChatBots,
    ChatBotsFaqs,
    ChatBotsDocLinks,
)
from models.chatModel.sharing import ChatBotSharing
from schemas.chatSchema.chatSchema import (
    ChatMessageRead,
    ChatSessionRead,
    CreateBot,
)
from models.chatModel.appearance import ChatSettings
from models.chatModel.tuning import DBInstructionPrompt
from sqlalchemy.orm import Session
from config import get_db
import os
from routes.chat.pinecone import (
    get_response_from_faqs,
    hybrid_retrieval,
    generate_response,
    delete_documents_from_pinecone,
)
from sqlalchemy import func, and_
from decorators.product_status import check_product_status
import secrets
import string
from datetime import datetime, time
from models.authModel.authModel import AuthUser
from email.utils import formataddr
from models.supportTickets.models import SupportTicket, Status

router = APIRouter()




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
    "audio/mpeg",  # .mp3
    "audio/wav",  # .wav
    "audio/x-wav",  # alternative .wav
    "audio/webm",  # .webm audio
    "audio/ogg",  # .ogg
    "audio/mp4",  # .m4a, .mp4 audio
    "audio/x-m4a",
    "application/vnd.ms-excel" "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.ms-excel.sheet.macroenabled.12",
    "application/vnd.ms-excel.template.macroenabled.12",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "application/vnd.ms-excel.addin.macroenabled.12",
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
        # Do NOT raise 404 if user_credits is None
        if user_credits is not None and user_credits.chatbots_allowed < len(owned_bots):
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
    user_id = None
    user_msg = data.get("message")
    bot_id = data.get("bot_id")

    try:

        # raise HTTPException(status_code=500, detail="Internal server error dsdsds   ")

        # Get user_id from access token
        token = request.cookies.get("access_token")
        if token:
            payload = decode_access_token(token)
            user_id = int(payload.get("user_id"))

        if not user_msg:
            raise HTTPException(status_code=400, detail="Message required")
        print("Geting Chatbot:", bot_id, "    :    ", token)
        # Get chatbot
        chatbot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="ChatBot not found")
        check_rate_limit(bot_id=bot_id, user_id=user_id, db=db, chatbot=chatbot)
        print("verify Token Limit")
        # Verify Message limit
        token_limit_available, message = verify_token_limit_available(
            bot_id=bot_id, db=db
        )
        if not token_limit_available:
            raise HTTPException(
                status_code=400, detail=f"Message limit exceeded: {message}"
            )

        # Verify chat session
        chat = db.query(ChatSession).filter(ChatSession.id == chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        message_history = get_recent_chat_history(chat_id=chat_id, db=db)
        response_from_faqs = get_response_from_faqs(user_msg, bot_id, db)
        response_content = response_from_faqs.answer if response_from_faqs else None

        active_tool = db.query(ToolsUsed).filter_by(status=True).first()

        if not response_content:
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

            creativity = chatbot.creativity
            text_content = chatbot.text_content

            if len(scores) > 0:
                # OpenAI with context
                generated_res = generate_response(
                    user_msg,
                    context=context_texts[:3],
                    use_openai=True,
                    instruction_prompts=dict_ins_prompt,
                    creativity=creativity,
                    text_content=text_content,
                    message_history=message_history,
                    active_tool=active_tool,
                )
            else:
                # Full OpenAI fallback
                generated_res = generate_response(
                    query=user_msg,
                    context=[],
                    use_openai=True,
                    instruction_prompts=dict_ins_prompt,
                    creativity=creativity,
                    text_content=text_content,
                    active_tool=active_tool,
                    message_history=message_history,
                )

            response_content = generated_res[0]
            request_tokens = generated_res[3] if len(generated_res) > 3 else 0
            openai_request_tokens = generated_res[1] if len(generated_res) > 1 else 0
            openai_response_tokens = generated_res[2] if len(generated_res) > 2 else 0
        else:
            request_tokens = openai_request_tokens = openai_response_tokens = 0

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

        # Validate response
        is_valid, reason = validate_response(response_content)
        if not is_valid:
            response_content = handle_invalid_response(
                question=user_msg,
                response=response_content,
                reason=reason,
                user_id=user_id,
                bot_id=bot_id,
                db=db,
            )

        # Update token usage
        consumed_token = SimpleNamespace(
            request_token=request_tokens,
            response_token=openai_response_tokens,
            open_ai_request_token=openai_request_tokens,
            open_ai_response_token=openai_response_tokens,
            request_message=1,
            response_message=1,
        )
        update_token_usage_on_consumption(
            consumed_token=consumed_token,
            consumed_token_type="direct_bot",
            bot_id=bot_id,
            db=db,
        )

        return bot_message

    except Exception as e:
        error_detail = str(e)
        # Log failed user message as SupportTicket
        if user_msg and bot_id:
            try:
                ticket = SupportTicket(
                    user_id=user_id,
                    subject=f"ChatBot Exception (chat_id={chat_id}, bot_id={bot_id})",
                    message=f"User Message: {user_msg}\n  Error Message: {error_detail}",
                    status=Status.issue_bug,
                    # error=f"User Message: {user_msg}\nError Message: {error_detail}"
                )
                db.add(ticket)
                db.commit()
            except Exception as db_exc:
                print("Failed to log SupportTicket:", db_exc)

        # Raise HTTP error
        raise HTTPException(status_code=500, detail=str(e))




async def check_available_char_limit(
    user_id: int,
    db: Session = Depends(get_db),
    new_chars: int = 0,  # characters being added in this operation
):
    # Get the user
    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get user's current active credit plan
    current_plan = db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
    if not current_plan or current_plan.expiry_date < datetime.utcnow():
        raise HTTPException(status_code=400, detail="No active user plan found")

    # Sum of all used characters (from all chatbots)
    total_chars_used = (
        db.query(func.sum(ChatBotsDocLinks.chars))
        .filter(ChatBotsDocLinks.user_id == user_id)
        .scalar()
        or 0
    )

    # Add chatbot `text_content` and FAQs characters to the total
    chatbots = db.query(ChatBots).filter(ChatBots.user_id == user_id).all()
    for chatbot in chatbots:
        if chatbot.text_content:
            total_chars_used += len(chatbot.text_content.strip())

        faqs = db.query(ChatBotsFaqs).filter(ChatBotsFaqs.bot_id == chatbot.id).all()
        for faq in faqs:
            question = faq.question.strip() if faq.question else ""
            answer = faq.answer.strip() if faq.answer else ""
            total_chars_used += len(question) + len(answer)

    # Add the characters the user is trying to save now
    total_with_new = total_chars_used + new_chars

    # Compare total used chars with allowed chars
    if total_with_new > current_plan.chars_allowed:
        remaining = max(0, current_plan.chars_allowed - total_chars_used)
        raise HTTPException(
            status_code=403,
            detail=f"Character limit exceeded. Available: {remaining}, Trying to add: {new_chars}. Please upgrade your plan.",
        )

    # If under limit, return remaining characters
    remaining = current_plan.chars_allowed - total_with_new
    return {
        "status": "ok",
        "total_used": total_chars_used,
        "allowed_limit": current_plan.chars_allowed,
        "remaining": remaining,
    }


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



@router.get("/tokens")
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

        if credits:
            token_usages = db.query(TokenUsage).filter_by(user_id=user_id).all()
            print(f"Fetched {len(token_usages)} token usage records")
            total_token_consumption = sum(
                usage.combined_token_consumption or 0 for usage in token_usages
            )
            print(f"Total token consumption: {total_token_consumption}")

            total_message_consumption = sum(
                usage.combined_message_consumption or 0 for usage in token_usages
            )
            print(f"Total token consumption: {total_message_consumption}")
            return {
                "credits": credits,
                "token_usage": token_usages,
                "total_token_consumption": total_token_consumption,
                "total_message_consumption": total_message_consumption,
                "has_shared_bots": False,
            }
        else:
            # Check for shared bots
            shared_records = (
                db.query(ChatBotSharing.bot_id, ChatBotSharing.owner_id)
                .filter(
                    ChatBotSharing.shared_user_id == user_id,
                    ChatBotSharing.status == "active",
                )
                .all()
            )
            shared_bot_ids = [record.bot_id for record in shared_records]
            shared_owner_ids = [record.owner_id for record in shared_records]
            print(json.dumps(shared_owner_ids))
            if shared_owner_ids:
                token_usages = (
                    db.query(TokenUsage)
                    .filter(TokenUsage.user_id.in_(shared_owner_ids))
                    .all()
                )
            if shared_bot_ids:
                print(
                    "User has shared bots, returning empty credits info with has_shared_bots True"
                )
                return {
                    "credits": None,
                    "token_usage": token_usages or [],
                    "total_token_consumption": 0,
                    "total_message_consumption": 0,
                    "has_shared_bots": True,
                }

            else:
                print("No credits and no shared bots found")
                raise HTTPException(status_code=404, detail="No Credit History Found")

    except HTTPException as http_exc:
        print(f"HTTPException: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        print("Unhandled exception in /tokens endpoint:", str(e))
        import traceback

        traceback.print_exc()
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

            # Calculate tokens and messages
            request_tokens = 0
            request_messages = 0
            if user_messages:
                combined_user_text = " ".join(user_messages)
                request_tokens = len(encoder.encode(combined_user_text))
                request_messages = len(user_messages)

            response_tokens = 0
            response_messages = 0
            if bot_messages:
                combined_bot_text = " ".join(bot_messages)
                cleaned_response = re.sub(
                    r"```(html|json)?", "", combined_bot_text, flags=re.IGNORECASE
                )
                cleaned_response = re.sub(r"```", "", cleaned_response)
                cleaned_response = cleaned_response.strip()

                # Remove HTML tags if the text appears to be in HTML format
                if re.search(r"<[a-z][\s\S]*>", cleaned_response, re.IGNORECASE):
                    cleaned_response = re.sub(r"<[^>]+>", "", cleaned_response)
                    cleaned_response = cleaned_response.strip()

                cleaned_response = re.sub(r"\s+", " ", cleaned_response).strip()
                response_tokens = len(encoder.encode(cleaned_response))
                response_messages = len(bot_messages)

            return {
                "request_tokens": request_tokens,
                "response_tokens": response_tokens,
                "users": len(user_ids),
                "request_messages": request_messages,
                "response_messages": response_messages,
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
            else {
                "request_tokens": 0,
                "response_tokens": 0,
                "users": 0,
                "request_messages": 0,
                "response_messages": 0,
            }
        )

        monthly_data = (
            process_messages(monthly_messages)
            if monthly_messages
            else {
                "request_tokens": 0,
                "response_tokens": 0,
                "users": 0,
                "request_messages": 0,
                "response_messages": 0,
            }
        )
        print(json.dumps(today_data))
        return {"today": today_data, "monthly": monthly_data}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





