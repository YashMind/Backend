from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response, Form
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from utils.utils import create_access_token, decode_access_token, create_reset_token, send_reset_email, decode_reset_access_token, get_current_user
from jose import JWTError, jwt
from uuid import uuid4
import json
from models.chatModel.chatModel import ChatSession, ChatMessage
from schemas.chatSchema.chatSchema import ChatMessageBase, ChatMessageCreate, ChatMessageRead, ChatSessionCreate, ChatSessionRead, ChatSessionWithMessages
from sqlalchemy.orm import Session
from config import get_db
from typing import Optional, List

from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage

llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7)

router = APIRouter()

# create new chat
@router.post("/chats", response_model=ChatSessionRead)
async def create_chat(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        print("user_id ", user_id)

        new_chat = ChatSession(user_id=user_id)
        db.add(new_chat)
        db.commit()
        db.refresh(new_chat)
        return new_chat
    
    except HTTPException as http_exc:
        print("http_exc ", http_exc)
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail="Internal server error")
    
# send message
@router.post("/chats/{chat_id}/message", response_model=ChatMessageRead)
async def chat_message(chat_id: int, data: dict, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        user_msg = data.get("message")
        if not user_msg:
            raise HTTPException(status_code=400, detail="Message required")

        # Verify chat belongs to user
        chat = db.query(ChatSession).filter_by(id=chat_id, user_id=user_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Get message history from DB
        messages = db.query(ChatMessage).filter_by(chat_id=chat_id).order_by(ChatMessage.created_at.asc()).all()

        langchain_messages = [
            HumanMessage(content=m.message) if m.sender == 'user' else AIMessage(content=m.message)
            for m in messages
        ]

        # Add current user message
        langchain_messages.append(HumanMessage(content=user_msg))

        # Call LLM
        response = llm(langchain_messages)

        # Save both user and bot messages
        db.add(ChatMessage(chat_id=chat_id, sender="user", message=user_msg))
        db.add(ChatMessage(chat_id=chat_id, sender="bot", message=response.content))
        db.commit()

        return {"response": response.content}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
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
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        chat = db.query(ChatSession).filter_by(id=chat_id, user_id=user_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

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



