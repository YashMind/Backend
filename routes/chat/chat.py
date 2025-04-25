from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response, Form,  UploadFile, File, Query
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from utils.utils import create_access_token, decode_access_token, get_current_user
from jose import JWTError, jwt
from uuid import uuid4
import json
from models.chatModel.chatModel import ChatSession, ChatMessage, ChatBots, ChatBotsFaqs
from schemas.chatSchema.chatSchema import ChatMessageBase, ChatMessageCreate, ChatMessageRead, ChatSessionCreate, ChatSessionRead, ChatSessionWithMessages, CreateBot, DeleteChatsRequest, CreateBotFaqs, FaqResponse
from schemas.authSchema.authSchema import User
from sqlalchemy.orm import Session
from config import get_db
from typing import Optional, Dict, List
from collections import defaultdict
import os
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage
from utils.utils import get_country_from_ip
# from routes.chat.pinecone import retrieve_answers
llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7)

router = APIRouter()

# create new chatbot
@router.post("/create-bot", response_model=CreateBot)
async def create_chatbot(data:CreateBot, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        new_chatbot = ChatBots(
            user_id=user_id,
            chatbot_name=data.chatbot_name,
            public= data.public,
            train_from=data.train_from,
            target_link=data.target_link,
            document_link=data.document_link
        )
        db.add(new_chatbot)
        db.commit()
        db.refresh(new_chatbot)
        return new_chatbot
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
# update chatbot
@router.put("/update-bot", response_model=CreateBot)
async def update_chatbot(data:CreateBot, db: Session = Depends(get_db)):
    try:
        chatbot = db.query(ChatBots).filter(ChatBots.id == int(data.id)).first()
        print("chatbot ", chatbot)
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

        db.commit()
        db.refresh(chatbot)
        return chatbot
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    
# get chatbot
@router.get("/get-bot", response_model=CreateBot)
async def get_chatbot(botId:int, db: Session = Depends(get_db)):
    try:
        chatbot = db.query(ChatBots).filter(ChatBots.id == botId).first()
        print("chatbot ", chatbot)
        if not chatbot:
            raise HTTPException(status_code=404, detail="Chatbot not found")
        return chatbot
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    
UPLOAD_DIRECTORY = "uploads/"
ALLOWED_FILE_TYPES = [
    "text/plain",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
]
@router.post("/upload-document")
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
        raise HTTPException(status_code=500, detail="An unexpected error occurred") from e

# get all chatbots
@router.get("/get-all", response_model=List[CreateBot])
async def get_my_bots(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        
        bots = db.query(ChatBots).filter(ChatBots.user_id == user_id).order_by(ChatBots.created_at.desc()).all()
        return bots
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

# create new chat
@router.post("/chats-id", response_model=ChatSessionRead)
async def create_chat(data: ChatSessionRead, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        bot_id = data.bot_id
        last_chat = (db.query(ChatSession).filter_by(user_id=user_id, bot_id=bot_id).order_by(ChatSession.created_at.desc()).first())

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
        raise HTTPException(status_code=500, detail="Internal server error")
    
# send message
@router.post("/chats/{chat_id}/message", response_model=ChatMessageRead)
async def chat_message(chat_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))


        user_msg = data.get("message")
        bot_id = data.get("bot_id")
        if not user_msg:
            raise HTTPException(status_code=400, detail="Message required")

        # Verify chat belongs to user
        chat = db.query(ChatSession).filter_by(id=chat_id, user_id=user_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        # Get user's country
        ip = request.client.host
        country = await get_country_from_ip(ip)
        print("country ", country)

        # pine cone
        # pinecone_answer = retrieve_answers(user_msg)
        pinecone_answer = False
        # If Pinecone answer is found and good
        if pinecone_answer and len(pinecone_answer.strip()) > 0:
            response_content = pinecone_answer
        else:
            # Get message history from DB
            messages = db.query(ChatMessage).filter_by(chat_id=chat_id).order_by(ChatMessage.created_at.asc()).all()

            langchain_messages = [
                HumanMessage(content=m.message) if m.sender == 'user' else AIMessage(content=m.message)
                for m in messages
            ]

            # Add current user message
            langchain_messages.append(HumanMessage(content=user_msg))

            # Call LLM
            response = llm.invoke(langchain_messages)
            response_content = response.content if response and response.content else "No response"

        # Save both user and bot messages
        user_message  = ChatMessage(user_id=user_id, bot_id=bot_id, chat_id=chat_id, sender="user", message=user_msg)
        bot_message = ChatMessage(user_id=user_id, bot_id=bot_id, chat_id=chat_id, sender="bot", message=response_content)

        db.add_all([user_message, bot_message])
        db.commit()
        db.refresh(bot_message)
        return bot_message
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail="Internal server error")
    
# get all charts
@router.get("/chats", response_model=List[ChatSessionWithMessages])
async def list_chats(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        chats = db.query(ChatSession).filter_by(user_id=user_id).order_by(ChatSession.created_at.desc()).all()
        return chats
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
    
# load chat history
@router.get("/chats/{chat_id}", response_model=List[ChatMessageRead])
async def get_chat_history(chat_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        chat = db.query(ChatSession).filter_by(id=chat_id, user_id=user_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        messages = db.query(ChatMessage).filter_by(chat_id=chat_id).order_by(ChatMessage.created_at.asc()).all()
        return messages
        # return [ChatMessageRead.from_orm(message) for message in messages]
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

# get user chat history
# response_model=Dict[int, List[ChatMessageRead]]
@router.get("/chats-history/{bot_id}")
async def get_user_chat_history(bot_id: int, request: Request, db: Session = Depends(get_db), 
    page: int = Query(1, ge=1), limit: int = Query(10, ge=1), search: Optional[str] = None):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        chat_bot = db.query(ChatBots).filter_by(id=bot_id, user_id=user_id).first()
        session_query = db.query(ChatSession).filter_by(bot_id=bot_id, user_id=user_id)
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
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.delete("/delete-chats/{bot_id}")
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/chats")
async def delete_all_chats(request: Request, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=500, detail="Internal server error")

# create new chatbot
@router.post("/create-bot-faqs", response_model=CreateBotFaqs)
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
        return new_chatbot_faq
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.get("/get-bot-faqs/{bot_id}", response_model=List[FaqResponse])
async def create_chatbot_faqs(bot_id:int, request: Request, db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=500, detail="Internal server error")
    
@router.delete("/delete-faq/{bot_id}/{faq_id}")
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
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/delete-all-faqs/{bot_id}")
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
        raise HTTPException(status_code=500, detail="Internal server error")




