from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from requests import Session

from config import get_db
from decorators.product_status import check_product_status
from models.chatModel.chatModel import  ChatBots,  ChatBotsFaqs
from routes.chat.chat import check_available_char_limit
from schemas.chatSchema.chatSchema import CreateBotFaqs, FaqResponse, UpdateBotFaqs
from utils.utils import decode_access_token


router = APIRouter()




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

        # Calculate total chars in the new FAQs
        new_chars = 0
        for qa in data.questions:
            question = qa.question.strip() if qa.question else ""
            answer = qa.answer.strip() if qa.answer else ""
            new_chars += len(question) + len(answer)
        
        if not data.bot_id:
            raise HTTPException(    status_code=400, detail="Chatbot id is required")
        
        bot = db.query(ChatBots).filter(ChatBots.id == data.bot_id).first()
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        # Check if adding these chars will exceed the limit
        await check_available_char_limit(user_id=bot.user_id, db=db, new_chars=new_chars)

        # If within limit, proceed to save
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

        return {"bot_id": data.bot_id, "questions": created_faqs}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        print("e ", e)
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/update-bot-faqs", response_model=UpdateBotFaqs)
@check_product_status("chatbot")
async def update_chatbot_faqs(
    data: UpdateBotFaqs, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        updated_faqs = []

        for qa in data.questions:
            existing_faq = db.query(ChatBotsFaqs).filter(
                ChatBotsFaqs.id == qa.faq_id,
                ChatBotsFaqs.user_id == user_id,
                ChatBotsFaqs.bot_id == data.bot_id
            ).first()
            
            if existing_faq:
                existing_faq.question = qa.question
                existing_faq.answer = qa.answer
                db.commit()
                db.refresh(existing_faq)
                updated_faqs.append(existing_faq)

        return {
            "bot_id": data.bot_id,
            "questions": [
                {"faq_id": faq.id, "question": faq.question, "answer": faq.answer}
                for faq in updated_faqs
            ],
        }

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
        print(token)

        chatbot_faqs = (
            db.query(ChatBotsFaqs)
            .filter_by(bot_id=bot_id)
            .order_by(ChatBotsFaqs.created_at.desc())
            .all()
        )

        if not chatbot_faqs:
            print(f"No FAQs found for user_id {user_id} and bot_id {bot_id}")
            return []
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

