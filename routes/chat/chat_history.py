from collections import defaultdict
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from requests import Session

from config import get_db
from decorators.product_status import check_product_status
from models.authModel.authModel import AuthUser
from models.chatModel.chatModel import  ChatBots, ChatMessage, ChatSession

from schemas.chatSchema.chatSchema import ChatMessageRead, ChatSessionWithMessages, DeleteChatsRequest
from utils.utils import decode_access_token


router = APIRouter()

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
async def get_chat_history_by_chat_id(
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
async def get_user_chat_history_by_user_id(
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


@router.get("/chats-history/{bot_id}")
@check_product_status("chatbot")
async def get_user_chat_history_by_bot_id(
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
        chat_bot = db.query(ChatBots).filter_by(id=bot_id).first()

        # Start with base query for sessions
        session_query = db.query(ChatSession).filter_by(bot_id=bot_id, archived=False)

        if not session_query:
            raise HTTPException(status_code=404, detail="Chat not found")

        if search:
            session_query = session_query.filter(
                ChatMessage.message.ilike(f"%{search}%")
            )

        # ORDER sessions by created_at descending to get most recent first
        session_query = session_query.order_by(ChatSession.created_at.desc())

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

        # Get messages for these sessions, ordered by created_at descending
        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.chat_id.in_(session_ids))
            .order_by(ChatMessage.created_at.desc())
            .all()
        )

        # Build a map of session_id to session (to get platform and created_at)
        session_map = {session.id: session for session in sessions}

        # Group messages by chat_id and include platform
        grouped_sessions = {}
        for message in messages:
            chat_id = message.chat_id
            if chat_id not in grouped_sessions:
                grouped_sessions[chat_id] = {
                    "platform": session_map[chat_id].platform,
                    "created_at": session_map[chat_id].created_at,  # Add this
                    "messages": [],
                }
            grouped_sessions[chat_id]["messages"].append(message)

        # Sort sessions by created_at descending (most recent first)
        sorted_grouped = dict(
            sorted(
                grouped_sessions.items(),
                key=lambda x: x[1]["created_at"],  # Sort by session's created_at
                reverse=True,
            )
        )

        return {
            "data": sorted_grouped,
            "totalCount": total_count,
            "totalPages": (total_count + limit - 1) // limit,
            "currentPage": page,
            "chatBot": chat_bot,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e))


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
