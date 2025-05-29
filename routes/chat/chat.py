from fastapi import APIRouter, Body, Depends, HTTPException, Request, UploadFile, File, Query, BackgroundTasks
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from utils.utils import decode_access_token, get_current_user
from uuid import uuid4
from sqlalchemy import or_, desc, asc
import json
from models.chatModel.chatModel import ChatSession, ChatMessage, ChatBots, ChatBotsFaqs, ChatBotsDocLinks, ChatBotsDocChunks, ChatBotLeadsModel, ChatTotalToken
from models.chatModel.sharing import ChatBotSharing
from schemas.chatSchema.chatSchema import ChatMessageRead, ChatSessionRead, ChatSessionWithMessages, CreateBot, DeleteChatsRequest, CreateBotFaqs, FaqResponse, CreateBotDocLinks, DeleteDocLinksRequest, ChatbotLeads, DeleteChatbotLeadsRequest, ChatMessageTokens, BotTokens
from schemas.chatSchema.sharingSchema import DirectSharingRequest, EmailInviteRequest, BulkEmailInviteRequest, AcceptInviteRequest, SharingResponse, InviteResponse, AcceptInviteResponse
from models.chatModel.appearance import ChatSettings
from models.chatModel.tuning import DBInstructionPrompt
from sqlalchemy.orm import Session
from config import get_db, settings
from typing import Optional, List
from collections import defaultdict
import os
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage
from routes.chat.pinecone import  clear_all_pinecone_namespaces, get_response_from_faqs, hybrid_retrieval, generate_response, delete_documents_from_pinecone
from sqlalchemy import func, and_
from routes.chat.celery_worker import process_document_task
from decorators.product_status import check_product_status
import secrets
import string
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from models.authModel.authModel import AuthUser

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7)

router = APIRouter()

def generate_invite_token():
    """Generate a random token for invitation links"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

async def send_invitation_email(recipient_email: str, invite_token: str, chatbot_name: str, owner_name: str):
    """Send invitation email to the recipient"""
    try:
        # Create message
        message = MIMEMultipart()
        message["From"] = settings.EMAIL_ADDRESS
        message["To"] = recipient_email
        message["Subject"] = f"You've been invited to collaborate on a chatbot: {chatbot_name}"

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
        generated_token = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(25))

        new_chatbot = ChatBots(
            user_id=user_id,
            chatbot_name=data.get("chatbot_name"),
            public= data.get("public"),
            train_from=data.get("train_from"),
            target_link=data.get("target_link"),
            document_link=data.get("document_link"),
            creativity=0,
            token=generated_token
        )
        db.add(new_chatbot)
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
async def update_chatbot(data:CreateBot, db: Session = Depends(get_db)):
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
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        chatbot = db.query(ChatBots).filter(ChatBots.id == botId).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="Chatbot not found")

        # Check if user is the owner
        if chatbot.user_id == user_id:
            return chatbot

        # Check if chatbot is shared with the user
        sharing = db.query(ChatBotSharing).filter(
            ChatBotSharing.bot_id == botId,
            ChatBotSharing.shared_user_id == user_id,
            ChatBotSharing.status == "active"
        ).first()

        if sharing:
            return chatbot

        # If chatbot is public, allow access
        if chatbot.public:
            return chatbot

        raise HTTPException(status_code=403, detail="You don't have access to this chatbot")

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e), error=e)

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
]


@router.post("/upload-document")
@check_product_status("chatbot")
async def upload_photo(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    try:
        # Validate file type
        if not os.path.exists(UPLOAD_DIRECTORY):
            os.makedirs(UPLOAD_DIRECTORY)

        if file.content_type not in ALLOWED_FILE_TYPES:
            raise HTTPException(status_code=400, detail="Invalid file type. Only image files are allowed.")

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

# get all chatbots
@router.get("/get-all", response_model=List[CreateBot])
@check_product_status("chatbot")
async def get_my_bots(request: Request, db: Session = Depends(get_db), include_shared: bool = Query(True)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Get user's own bots
        owned_bots = db.query(ChatBots).filter(ChatBots.user_id == user_id).order_by(ChatBots.created_at.desc()).all()

        # If include_shared is True, also get shared bots
        if include_shared:
            # Get IDs of bots shared with the user
            shared_bot_ids = db.query(ChatBotSharing.bot_id).filter(
                ChatBotSharing.shared_user_id == user_id,
                ChatBotSharing.status == "active"
            ).all()

            # Extract IDs from result tuples
            shared_bot_ids = [bot_id for (bot_id,) in shared_bot_ids]

            # Get shared bots if there are any
            if shared_bot_ids:
                shared_bots = db.query(ChatBots).filter(ChatBots.id.in_(shared_bot_ids)).all()
                # Combine owned and shared bots
                return owned_bots + shared_bots

        return owned_bots
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# create new chat
@router.post("/chats-id", response_model=ChatSessionRead)
@check_product_status("chatbot")
async def create_chat(data: ChatSessionRead, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        bot_id = data.bot_id
        last_chat = (db.query(ChatSession).filter(ChatSession.user_id==user_id, ChatSession.bot_id==bot_id).order_by(ChatSession.created_at.desc()).first())

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
async def create_chat_token_session(data: ChatSessionRead, request: Request, db: Session = Depends(get_db)):
    try:
        chat_bot = db.query(ChatBots).filter_by(token=data.token).first()
        if not chat_bot:
            raise HTTPException(status_code=404, detail="ChatBot not found with given token")
        if not chat_bot.public:
        # Step 2: Check if it has any messages
            token = request.cookies.get("access_token")
            if not token:
                raise HTTPException(status_code=401, detail="Authentication required for private chatbot")
            payload = decode_access_token(token)
            user_id = int(payload.get("user_id"))
            existing_chat = db.query(ChatSession).filter_by(bot_id=chat_bot.id, user_id=user_id).first()
            if existing_chat:
                return existing_chat

            new_chat = ChatSession(token=data.token, bot_id=chat_bot.id, user_id=user_id)
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
async def chat_message(chat_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
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

        chatbot = db.query(ChatBots).filter(ChatBots.id==bot_id).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="ChatBot not found")

        token_record = db.query(ChatTotalToken).filter(ChatTotalToken.user_id==user_id , ChatTotalToken.bot_id==bot_id).first()
        # currently we are only checking if the reacord in this table exsits then it should not exceed limit. once subscriptions implemented we will return user with no token limit if the record not exists
        if token_record:
            if token_record.total_token <= token_record.user_message_tokens:
                raise HTTPException(status_code=400, detail="Token limit exceeded")


        # Verify chat belongs to user
        chat = db.query(ChatSession).filter(ChatSession.id==chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")


        user_tokens, response_tokens, openai_tokens = 0, 0, 0
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

        response_content= response_from_faqs.answer if response_from_faqs else None


        if not response_content:
            print("No response found from FAQ")
            # Hybrid retrieval
            context_texts, scores = hybrid_retrieval(user_msg, bot_id)

            instruction_prompts = db.query(DBInstructionPrompt).filter(DBInstructionPrompt.bot_id==bot_id).all()
            dict_ins_prompt = [{prompt.type: prompt.prompt} for prompt in instruction_prompts]
            # print("DICT INSTRUCTION PROMPTS",dict_ins_prompt)
            
            creativity = chatbot.creativity
            text_content = chatbot.text_content

            answer = None
            print("Hybrid retrieval results: ", context_texts, scores)
            # Determine answer source

            if any(score > 0.85 for score in scores):
                print("using openai with context")
                use_openai = True
                generated_res = generate_response(user_msg, context_texts[:3], use_openai, dict_ins_prompt, creativity, text_content)
                answer = generated_res[0]
                openai_tokens = generated_res[1]
                print("ANSWER",answer, openai_tokens)

            else:
                print("no direct scores from hybrid retrieval and using openai independently")
                # Full OpenAI fallback
                use_openai = True
                generated_res = generate_response(user_msg, [], use_openai, dict_ins_prompt, creativity, text_content)
                answer = generated_res[0]
                openai_tokens = generated_res[1]
                print("ANSWER",answer, openai_tokens)

            response_content= answer

        # ✅ Always compute tokens after final response is ready
        user_tokens = len(user_msg.strip().split())
        response_tokens = len(response_content.strip().split() if response_content else "No response found")

        # Save user and bot messages
        user_message = ChatMessage(user_id=user_id, bot_id=bot_id, chat_id=chat_id, sender="user", message=user_msg)
        bot_message = ChatMessage(user_id=user_id, bot_id=bot_id, chat_id=chat_id, sender="bot", message=response_content)

        db.add_all([user_message, bot_message])
        db.commit()
        db.refresh(bot_message)
        print("BOT MESSAGE SAVED")

        bot_message.input_tokens = user_tokens
        bot_message.output_tokens = response_tokens
        bot_message.open_ai_tokens = openai_tokens

        # ✅ Update ChatTotalToken
        token_record = db.query(ChatTotalToken).filter(ChatTotalToken.user_id==user_id , ChatTotalToken.bot_id==bot_id).first()
        print("TOKEN RECORDS GENERATING")
        if token_record:
            token_record.user_message_tokens += user_tokens
            token_record.response_tokens += response_tokens
            token_record.openai_tokens += openai_tokens
            token_record.updated_at = func.now()
        else:
            token_record = ChatTotalToken(
                user_id=user_id,
                bot_id=bot_id,
                total_token=10000,  # default total
                user_message_tokens = user_tokens,
                response_tokens = response_tokens,
                openai_tokens = openai_tokens,
                plan="basic"
            )
            db.add(token_record)

        db.commit()

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

        chats = db.query(ChatSession).filter_by(user_id=user_id ,archived =False).order_by(ChatSession.created_at.desc()).all()
        return chats
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# load chat history
@router.get("/chats/{chat_id}", response_model=List[ChatMessageRead])
@check_product_status("chatbot")
async def get_chat_history(chat_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        chat = db.query(ChatSession).filter_by(id=chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        messages = db.query(ChatMessage).filter_by(chat_id=chat_id).order_by(ChatMessage.created_at.asc()).all()
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
    search: Optional[str] = None
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
                user_id=user_id,
                archived=True,
                bot_id=chat_bot.id
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
                response_data.append({
                    "chatBotId": chat_bot.id,
                    "chatBotName": chat_bot.chatbot_name,
                    "sessions": [],
                    "totalCount": 0,
                    "totalPages": 0,
                    "currentPage": page
                })
                continue

            # Get messages for these sessions
            session_ids = [int(s.id) for s in sessions]
            messages = db.query(ChatMessage).filter(
                ChatMessage.chat_id.in_(session_ids)
            ).order_by(ChatMessage.created_at.asc()).all()

            # Group messages
            grouped_messages = defaultdict(list)
            for message in messages:
                grouped_messages[message.chat_id].append(message)

            # Convert to dict and sort
            sorted_grouped = dict(sorted(
                grouped_messages.items(),
                key=lambda x: x[0],
                reverse=True
            ))

            response_data.append({
                "chatBotId": chat_bot.id,
                "chatBotName": chat_bot.chatbot_name,
                "sessions": sorted_grouped,
                "totalCount": total_count,
                "totalPages": (total_count + limit - 1) // limit,
                "currentPage": page
            })

        return {
            "data": jsonable_encoder(response_data),
            "globalTotal": sum(item["totalCount"] for item in response_data),
            "globalPages": (sum(item["totalCount"] for item in response_data) + limit - 1) // limit
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(f"Error fetching chat history: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

# get user chat history
@router.get("/chats-history/{bot_id}")
@check_product_status("chatbot")
async def get_user_chat_history(bot_id: int, request: Request, db: Session = Depends(get_db),
    page: int = Query(1, ge=1), limit: int = Query(10, ge=1), search: Optional[str] = None):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        chat_bot = db.query(ChatBots).filter_by(id=bot_id, user_id=user_id).first()
        session_query = db.query(ChatSession).filter_by(bot_id=bot_id, user_id=user_id, archived=False)
        if not session_query:
            raise HTTPException(status_code=404, detail="Chat not found")
        if search:
            session_query = session_query.filter(ChatMessage.message.ilike(f"%{search}%"))

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
                "chatBot":chat_bot
            }

        messages = db.query(ChatMessage).filter(ChatMessage.chat_id.in_(session_ids)).order_by(ChatMessage.created_at.asc()).all()
        # Group messages by chat_id
        grouped_messages = defaultdict(list)
        for message in messages:
            grouped_messages[message.chat_id].append(message)
        sorted_grouped = dict(sorted(grouped_messages.items(), key=lambda x: x[0], reverse=True))
        return {
            "data": sorted_grouped,
            "totalCount": total_count,
            "totalPages": (total_count + limit - 1) // limit,
            "currentPage": page,
            "chatBot": chat_bot
        }
        # return sorted_grouped
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e))# get user chat history





@router.delete("/delete-chats/{bot_id}")
@check_product_status("chatbot")
async def delete_chat(bot_id: int, request_data: DeleteChatsRequest, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        for chat_id in request_data.chat_ids:
            chat = db.query(ChatSession).filter_by(id=chat_id, user_id=user_id, bot_id=bot_id).first()
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
            bot_chats = db.query(ChatSession).filter(ChatSession.bot_id==bot.id).all()
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
            user_chats = db.query(ChatSession).filter(ChatSession.bot_id == bot.id).all()
            for chat in user_chats:
                chat.archived = True

        db.commit()

        return {"message": "All chats archived successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# create new chatbot
@router.post("/create-bot-faqs", response_model=CreateBotFaqs)
@check_product_status("chatbot")
async def create_chatbot_faqs(data:CreateBotFaqs, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        created_faqs = []

        for qa in data.questions:
            new_chatbot_faq = ChatBotsFaqs(
                user_id=user_id,
                bot_id=data.bot_id,
                question= qa.question,
                answer=qa.answer
            )
            db.add(new_chatbot_faq)
            db.commit()
            db.refresh(new_chatbot_faq)
            created_faqs.append(new_chatbot_faq)
            # return new_chatbot_faq

        return {
            'bot_id': data.bot_id,
            'questions':created_faqs}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-bot-faqs/{bot_id}", response_model=List[FaqResponse])
@check_product_status("chatbot")
async def get_chatbot_faqs(bot_id:int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        chatbot_faqs = db.query(ChatBotsFaqs).filter_by(bot_id=bot_id, user_id=user_id).order_by(ChatBotsFaqs.created_at.desc()).all()
        return chatbot_faqs

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete-faq/{bot_id}/{faq_id}")
@check_product_status("chatbot")
async def delete_single_faq(bot_id: int, faq_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        faq = db.query(ChatBotsFaqs).filter_by(id=faq_id, bot_id=bot_id, user_id=user_id).first()
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
        deleted = db.query(ChatBotsFaqs).filter_by(bot_id=bot_id, user_id=user_id).delete()
        db.commit()

        return {"message": f"{deleted} FAQs deleted successfully."}
    except Exception as e:
        print("Delete all FAQs error:", e)
        raise HTTPException(status_code=500, detail=str(e))

# create new chatbot doc
@router.post("/create-bot-doc-links", response_model=CreateBotDocLinks)
@check_product_status("chatbot")
async def create_chatbot_docs(data:CreateBotDocLinks, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        new_chatbot_doc_links = data
        new_chatbot_doc_links.user_id = user_id
        new_doc = ChatBotsDocLinks(
            user_id=user_id,
            bot_id=int(data.bot_id),
            chatbot_name=data.chatbot_name,
            train_from=data.train_from,
            target_link=data.target_link,
            document_link=data.document_link,
            public= data.public,
            status="pending",
            chars=0
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
    search: Optional[str] = Query(None, description="Search by document_link or target_link"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(ChatBotsDocLinks).filter(ChatBotsDocLinks.user_id == user_id, ChatBotsDocLinks.bot_id==bot_id)

        total_target_links = db.query(ChatBotsDocLinks)\
        .filter(
            ChatBotsDocLinks.user_id == user_id,
            ChatBotsDocLinks.bot_id == bot_id,
            and_(
                ChatBotsDocLinks.target_link.isnot(None),
                ChatBotsDocLinks.target_link != ""
            )
        ).count()
        
        user_target_links = db.query(ChatBotsDocLinks)\
        .filter(
            ChatBotsDocLinks.user_id == user_id,
            and_(
                ChatBotsDocLinks.target_link.isnot(None),
                ChatBotsDocLinks.target_link != ""
            )
        ).count()

        # Count where document_link is not null and not empty
        total_document_links = db.query(ChatBotsDocLinks)\
            .filter(
                ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                and_(
                    ChatBotsDocLinks.document_link.isnot(None),
                    ChatBotsDocLinks.document_link != ""
                )
            ).count()

        total_chars = db.query(func.sum(ChatBotsDocLinks.chars))\
        .filter_by(user_id=user_id, bot_id=bot_id)\
        .scalar() or 0
        user_total_chars = db.query(func.sum(ChatBotsDocLinks.chars))\
        .filter_by(user_id=user_id)\
        .scalar() or 0


        pending_count = db.query(func.count(ChatBotsDocLinks.id))\
        .filter(ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.bot_id == bot_id,
                ChatBotsDocLinks.status == "Pending")\
        .scalar()
        
        user_pending_count = db.query(func.count(ChatBotsDocLinks.id))\
        .filter(ChatBotsDocLinks.user_id == user_id,
                ChatBotsDocLinks.status == "Pending")\
        .scalar()

        failed_count = db.query(func.count(ChatBotsDocLinks.id))\
            .filter(ChatBotsDocLinks.user_id == user_id,
                    ChatBotsDocLinks.bot_id == bot_id,
                    ChatBotsDocLinks.status == "Failed")\
            .scalar()
        user_failed_count = db.query(func.count(ChatBotsDocLinks.id))\
            .filter(ChatBotsDocLinks.user_id == user_id,
                    ChatBotsDocLinks.status == "Failed")\
            .scalar()

        indexed_count = db.query(func.count(ChatBotsDocLinks.id))\
            .filter(ChatBotsDocLinks.user_id == user_id,
                    ChatBotsDocLinks.bot_id == bot_id,
                    ChatBotsDocLinks.status == "Indexed")\
            .scalar()
        user_indexed_count = db.query(func.count(ChatBotsDocLinks.id))\
            .filter(ChatBotsDocLinks.user_id == user_id,
                    ChatBotsDocLinks.status == "Indexed")\
            .scalar()

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
            "data": results,
            "Indexed": 2,
            "total_target_links":total_target_links,
            "total_document_links":total_document_links,
            "pending_count":pending_count,
            "failed_count":failed_count,
            "indexed_count": indexed_count,
            "total_chars": total_chars,
            "user_target_links": user_target_links,
            "user_pending_count":user_pending_count,
            "user_failed_count":user_failed_count,
            "user_indexed_count":user_indexed_count,
            "user_total_chars":user_total_chars,
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
    db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # First get all document links that will be deleted
        docs_to_delete = db.query(ChatBotsDocLinks).filter(
            ChatBotsDocLinks.id.in_(request_data.doc_ids),
            ChatBotsDocLinks.user_id == user_id,
            ChatBotsDocLinks.bot_id == bot_id
        ).all()

        if not docs_to_delete:
            return {"message": "No documents found to delete"}

        # Get the source links for Pinecone deletion
        doc_links = [doc.target_link or doc.document_link for doc in docs_to_delete]

        # Delete from Pinecone first
        deletion_stats = delete_documents_from_pinecone(bot_id, doc_links, db)
        
        # # Clear whole pinecone
        # clear_all_pinecone_namespaces(db)

        # Then delete from database
        db.query(ChatBotsDocLinks).filter(
            ChatBotsDocLinks.id.in_(request_data.doc_ids),
            ChatBotsDocLinks.user_id == user_id,
            ChatBotsDocLinks.bot_id == bot_id
        ).delete(synchronize_session=False)

        db.commit()

        return {
            "message": "Documents deleted successfully",
            "pinecone_deletion_stats": deletion_stats
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
        chat_session = db.query(ChatSession).filter(ChatSession.token==token).first()
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

@router.delete("/delete-bot/{bot_id}")
@check_product_status("chatbot")
async def delete_chat(bot_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Delete in correct order if not using ON DELETE CASCADE
        db.query(ChatBotsFaqs).filter(ChatBotsFaqs.bot_id == bot_id).delete(synchronize_session=False)
        db.query(ChatBotsDocChunks).filter(ChatBotsDocChunks.bot_id == bot_id).delete(synchronize_session=False)
        db.query(ChatBotsDocLinks).filter(ChatBotsDocLinks.bot_id == bot_id).delete(synchronize_session=False)
        db.query(DBInstructionPrompt).filter(DBInstructionPrompt.bot_id == bot_id).delete(synchronize_session=False)
        db.query(ChatSettings).filter(ChatSettings.bot_id == bot_id).delete(synchronize_session=False)
        db.query(ChatMessage).filter(ChatMessage.bot_id == bot_id).delete(synchronize_session=False)
        db.query(ChatSession).filter(ChatSession.bot_id == bot_id).delete(synchronize_session=False)

        db.query(ChatBots).filter(ChatBots.id == bot_id, ChatBots.user_id == user_id).delete(synchronize_session=False)
        db.commit()
        return {"message": "Chatbot with all data deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# create new chatbot
@router.post("/create-bot-leads", response_model=ChatbotLeads)
@check_product_status("chatbot")
async def create_chatbot_leads(data:ChatbotLeads, request: Request, db: Session = Depends(get_db)):
    try:
        chatbot = db.query(ChatBots).filter(ChatBots.id == data.bot_id).first()
        if not chatbot:
            raise HTTPException(status_code=404,detail="Chatbot not found")

        user_id=None

        # Require auth if chatbot is NOT public
        if not chatbot.public:
            token = request.cookies.get("access_token")
            if not token:
                raise HTTPException(status_code=401, detail="Unauthorized: Token missing")

            payload = decode_access_token(token)
            if not payload or "user_id" not in payload:
                raise HTTPException(status_code=401, detail="Unauthorized: Invalid token")

            user_id = int(payload["user_id"])
        else:
            user_id = None

        new_chatbot_lead = ChatBotLeadsModel(
            user_id=user_id or None,
            bot_id=data.bot_id,
            chat_id=data.chat_id,
            name= data.name,
            email=data.email,
            contact=data.contact,
            message=data.message,
            type=data.type
        )
        db.add(new_chatbot_lead)
        db.commit()
        db.refresh(new_chatbot_lead)
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
    search: Optional[str] = Query(None, description="Search by document_link or target_link"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(ChatBotLeadsModel).filter( ChatBotLeadsModel.bot_id==bot_id)

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
            "data": results
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete-chatbot-leads/{bot_id}")
@check_product_status("chatbot")
async def delete_doc_links(bot_id: int, request_data: DeleteChatbotLeadsRequest, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        for lead_id in request_data.lead_ids:
            doc = db.query(ChatBotLeadsModel).filter_by(id=lead_id, user_id=user_id, bot_id=bot_id).first()
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
async def chat_lead_messages(chat_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        messages = db.query(ChatMessage).filter(ChatMessage.chat_id==chat_id).order_by(ChatMessage.created_at.asc()).all()
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
            raise HTTPException(status_code=401, detail="Access token missing")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        bots = db.query(ChatBots).filter(ChatBots.user_id == user_id).all()

        bot_tokens_list = []
        total_tokens = 0

        for bot in bots:
            messages = db.query(ChatMessage).filter(
                ChatMessage.bot_id == bot.id,
                ChatMessage.user_id == user_id,
                ChatMessage.sender == 'user'
            ).all()

            # Get current date info
            now = datetime.utcnow()
            today = now.date()
            first_of_month = today.replace(day=1)

            # Initialize counters
            total_token_count = 0
            today_token_count = 0
            monthly_token_count = 0

            for msg in messages:
                if not msg.message:
                    continue

                word_count = len(msg.message.strip().split())
                total_token_count += word_count

                # Ensure message.created_at is a datetime
                created_at = msg.created_at.date() if hasattr(msg, "created_at") else None
                if created_at:
                    if created_at == today:
                        today_token_count += word_count
                    if created_at >= first_of_month:
                        monthly_token_count += word_count

            bot_tokens_list.append(BotTokens(
                bot_id=str(bot.id),
                tokens=total_token_count,
                token_today=today_token_count,
                token_monthly=monthly_token_count,
                messages=len(messages)
            ))
            total_tokens += total_token_count

        return ChatMessageTokens(
            total_tokens=total_tokens,
            bots=bot_tokens_list
        )

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print(str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/invite-users", response_model=InviteResponse)
@check_product_status("chatbot")
async def invite_users(
    data: BulkEmailInviteRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db)
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
        chatbot = db.query(ChatBots).filter(
            ChatBots.id == data.bot_id,
            ChatBots.user_id == owner_id
        ).first()

        if not chatbot:
            raise HTTPException(status_code=404, detail="Chatbot not found or you don't have permission")

        # Process each email
        invites = []
        for email in data.user_emails:
            # Check if user with this email exists
            user = db.query(AuthUser).filter(AuthUser.email == email).first()

            # Check if sharing already exists
            existing_share = None
            if user:
                existing_share = db.query(ChatBotSharing).filter(
                    ChatBotSharing.bot_id == data.bot_id,
                    ChatBotSharing.shared_user_id == user.id
                ).first()
            else:
                existing_share = db.query(ChatBotSharing).filter(
                    ChatBotSharing.bot_id == data.bot_id,
                    ChatBotSharing.shared_email == email
                ).first()

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
                    owner_name
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
                    status="pending"
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
                    owner_name
                )

        return {
            "message": f"Invitations sent to {len(invites)} users",
            "invites": invites
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/accept-invite/{token}", response_model=AcceptInviteResponse)
async def accept_invite(
    token: str,
    request: Request,
    db: Session = Depends(get_db)
):
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
        invitation = db.query(ChatBotSharing).filter(
            ChatBotSharing.invite_token == token,
            ChatBotSharing.status == "pending"
        ).first()

        if not invitation:
            raise HTTPException(status_code=404, detail="Invalid or expired invitation")

        # Check if the invitation matches the current user's email
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if invitation.shared_email and invitation.shared_email != user.email:
            raise HTTPException(
                status_code=403,
                detail="This invitation was sent to a different email address"
            )

        # Update the invitation
        invitation.shared_user_id = user_id
        invitation.status = "active"
        invitation.updated_at = datetime.now()

        db.commit()
        db.refresh(invitation)

        return {
            "message": "Invitation accepted successfully",
            "sharing": invitation
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/shared-chatbots", response_model=List[SharingResponse])
async def get_shared_chatbots(
    request: Request,
    db: Session = Depends(get_db)
):
    """Get all chatbots shared with the current user"""
    try:
        # Get current user from token
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Find all active sharing records for this user
        shared_chatbots = db.query(ChatBotSharing).filter(
            ChatBotSharing.shared_user_id == user_id,
            ChatBotSharing.status == "active"
        ).all()

        return shared_chatbots

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/revoke-sharing/{sharing_id}", response_model=SharingResponse)
async def revoke_sharing(
    sharing_id: int,
    request: Request,
    db: Session = Depends(get_db)
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
        sharing = db.query(ChatBotSharing).filter(
            ChatBotSharing.id == sharing_id
        ).first()

        if not sharing:
            raise HTTPException(status_code=404, detail="Sharing record not found")

        # Check if the current user is the owner
        if sharing.owner_id != user_id:
            raise HTTPException(status_code=403, detail="You don't have permission to revoke this sharing")

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
