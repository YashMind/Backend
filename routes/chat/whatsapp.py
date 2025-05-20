from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime
from twilio.rest import Client
from models.chatModel.integrations import WhatsAppUser  
from config import Settings,get_db
from sqlalchemy.orm import Session
from fastapi import APIRouter, Form, Depends, Response
import logging
from utils.utils import get_response_from_chatbot
from dotenv import load_dotenv
import os
from decorators.product_status import check_product_status

# Find your Account SID and Auth Token at twilio.com/console
# and set the environment variables. See http://twil.io/secure
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = Settings.TWILIO_AUTH_TOKEN
twilio_number = Settings.TWILIO_NUMBER

twilio_client = Client(account_sid, auth_token)


router = APIRouter()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# Single Twilio account (from settings)

@router.post("/register")
@check_product_status("chatbot")
async def register_whatsapp_user(
   request:Request,
    db: Session = Depends(get_db)
):
    
    data = await request.json()
    if 'bot_id' not in data or 'whatsapp_number' not in data:
        raise HTTPException(status_code=400, detail="Incomplete request data: bot_id and phone number are required")
    
    bot_id = data.get('bot_id')
    whatsapp_number = data.get('whatsapp_number')

    # Validate WhatsApp number format (basic check)
    if not whatsapp_number.startswith("+"):
        raise HTTPException(status_code=400, detail="WhatsApp number must include country code (e.g., +1234567890)")

    # Check if number already exists
    existing = db.query(WhatsAppUser).filter_by(whatsapp_number=whatsapp_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="This WhatsApp number is already registered")

    # Save to DB
    new_user = WhatsAppUser(
        bot_id=bot_id,
        whatsapp_number=whatsapp_number,
        created_at=datetime.utcnow()
    )
    

    # Send welcome message
    try:
        # print(account_sid, auth_token)
        # twilio_client = Client(account_sid, auth_token)
        
        twilio_client.messages.create(
            body="🚀 Welcome to the bot! You're now registered. Send a message to start chatting.",
            from_='whatsapp:+14155238886',  # Hardcoded for testing
            to=f'whatsapp:{whatsapp_number}'
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to send welcome message: {str(e)}")
    
    db.add(new_user)
    db.commit()
    return {"status": "success", "message": "WhatsApp user registered successfully"}


@router.post("/message")
@check_product_status("chatbot")
async def handle_whatsapp_message(
    From: str = Form(...),  # User's WhatsApp number (+1234567890)
    Body: str = Form(...),  # Message content
    db: Session = Depends(get_db)
):
    try:
        # Check if the sender is registered
        user = db.query(WhatsAppUser).filter_by(whatsapp_number=From.split(":")[1]).first()
        if not user:
            print("User not found")
            return Response(status_code=404)  # Ignore messages from unregistered numbers

        # Get bot response
        response_text = get_response_from_chatbot(
            data={
                'message': Body,
                'bot_id': user.bot_id,
                'token': user.whatsapp_number 
            },
            platform="whatsapp",
            db=db
        )
        

        # Send reply
        twilio_client.messages.create(
            from_=f"whatsapp:{twilio_number}",
            body=response_text,
            to=From
        )

        return Response(status_code=200)
    except Exception as e:
        raise  HTTPException(status_code=500, detail="Some error occured")