from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
import httpx
from requests import Session
from sqlalchemy import asc, desc, or_

from config import get_db
from decorators.product_status import check_product_status
from models.chatModel.chatModel import ChatBotLeadsModel, ChatBots, ChatMessage
from models.chatModel.integrations import ZapierIntegration
from routes.supportTickets.routes import send_email
from schemas.chatSchema.chatSchema import ChatMessageRead, ChatbotLeads, DeleteChatbotLeadsRequest
from utils.utils import decode_access_token, verify_chatbot_ownership


router = APIRouter()


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

        # Create email content
        email_html = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>New Lead Generated</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background-color: #4f46e5;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    padding: 20px;
                    border: 1px solid #e5e7eb;
                    border-top: none;
                    border-radius: 0 0 8px 8px;
                }}
                .lead-details {{
                    margin-bottom: 20px;
                }}
                .detail-row {{
                    margin-bottom: 10px;
                }}
                .detail-label {{
                    font-weight: bold;
                    display: inline-block;
                    width: 100px;
                }}
                .footer {{
                    margin-top: 20px;
                    font-size: 12px;
                    color: #6b7280;
                    text-align: center;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>New Lead Generated</h1>
            </div>
            <div class="content">
                <p>Hello,</p>
                <p>A new lead has been generated from your chatbot. Here are the details:</p>
                
                <div class="lead-details">
                    <div class="detail-row">
                        <span class="detail-label">Chatbot:</span>
                        <span>{chatbot_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Name:</span>
                        <span>{lead_name}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Email:</span>
                        <span>{lead_email}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Contact:</span>
                        <span>{lead_contact}</span>
                    </div>
                    <div class="detail-row">
                        <span class="detail-label">Message:</span>
                        <span>{lead_message}</span>
                    </div>
                </div>
                
                <p>Please follow up with this lead as soon as possible.</p>
            </div>
            <div class="footer">
                <p>This is an automated message. Please do not reply directly to this email.</p>
                <p>&copy; {current_year} Your Company Name. All rights reserved.</p>
            </div>
        </body>
        </html>
        """.format(
            chatbot_name=chatbot.chatbot_name,
            lead_name=new_chatbot_lead.name or "",
            lead_email=new_chatbot_lead.email or "",
            lead_contact=new_chatbot_lead.contact or "",
            lead_message=new_chatbot_lead.message or "",
            current_year=datetime.now().year,
        )
        print("EMAIL TEMPLATE GENERATED")
        if not chatbot.lead_email:
            print(
                "Warning: No lead email configured for chatbot, skipping email notification"
            )
        else:
            send_email(
                subject="New Lead generated",
                html_content=email_html,
                recipients=[chatbot.lead_email],
            )

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


@router.post("/configure-lead-mail", response_model=ChatbotLeads)
@check_product_status("chatbot")
async def configure_email_for_chatbot_lead(
    request: Request, config=Body(...), db: Session = Depends(get_db)
):
    """
    Configure email notifications for chatbot leads

    Args:
        bot_id: ID of the chatbot to configure
        email: Email address to receive notifications
    """
    try:
        bot_id = config.get("bot_id")
        # Get the chatbot from database
        chatbot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()

        if not chatbot:
            raise HTTPException(
                status_code=404,
                detail=f"Chatbot with ID {bot_id} not found",
            )

        # Update the email configuration
        chatbot.lead_email = config.get("email")

        # Commit changes
        db.add(chatbot)
        db.commit()
        db.refresh(chatbot)

        return {
            "success": True,
            "message": "Email configuration updated successfully",
            "data": {
                "bot_id": chatbot.id,
                "lead_email": chatbot.lead_email,
            },
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to update email configuration: {str(e)}"
        )


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

@router.delete("/delete-chatbot-leads/{bot_id}")
@check_product_status("chatbot")
async def delete_chat_leads(
    bot_id: int,
    request_data: DeleteChatbotLeadsRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        
        verified =await verify_chatbot_ownership(user_id=user_id, bot_id=bot_id,db=db)
        if not verified:
            raise HTTPException(status_code=402, detail="User not have authorization for this bot")
        for lead_id in request_data.lead_ids:

            
            lead = (
                    db.query(ChatBotLeadsModel)
                    .filter(
                        ChatBotLeadsModel.id == lead_id,
                        ChatBotLeadsModel.bot_id == bot_id
                    )
                    .first()
            )
            if lead:
                db.delete(lead)
                
        db.commit()
        return {"message": "Chatbot leads deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
