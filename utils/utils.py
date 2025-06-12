from base64 import b64encode
from types import SimpleNamespace
from fastapi import HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional
from sqlalchemy.orm import Session
from config import get_db
from models.adminModel.toolsModal import ToolsUsed
from models.chatModel.tuning import DBInstructionPrompt
from routes.chat.pinecone import (
    generate_response,
    get_response_from_faqs,
    hybrid_retrieval,
)
from models.authModel.authModel import AuthUser
from langchain.chat_models import ChatOpenAI
from models.chatModel.chatModel import ChatBots, ChatSession, ChatMessage
from langchain.schema import HumanMessage, AIMessage
from email.mime.text import MIMEText
import smtplib
import httpx

from routes.subscriptions.token_usage import (
    update_token_usage_on_consumption,
    verify_token_limit_available,
)

SECRET_KEY = "ADMIN@1234QWER"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 20160  # 2 weeks
RESET_PASSWORD_TOKEN_EXPIRE_MINUTES = 15


def get_response_from_chatbot(data, platform, db: Session):
    try:
        user_msg = data.get("message")
        bot_id = data.get("bot_id")
        token = data.get("token")

        if not user_msg:
            raise HTTPException(status_code=400, detail="Message required")

        token_limit_availabe, message = verify_token_limit_available(
            bot_id=bot_id, db=db
        )
        if not token_limit_availabe:
            # raise HTTPException(
            #     status_code=400, detail=f"Token limit exceeded: {message}"
            # )
            return "Sorry can't reply you at the moment, Token Limit exceeded"

        chatbot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="ChatBot not found")

        chat = db.query(ChatSession).filter_by(token=token).first()
        if not chat:
            chat = ChatSession(token=token, platform=platform, bot_id=bot_id)
            db.add(chat)
            db.commit()

        (
            request_tokens,
            response_tokens,
            openai_request_tokens,
            openai_response_tokens,
        ) = (0, 0, 0, 0)
        response_from_faqs = get_response_from_faqs(user_msg, bot_id, db)

        response_content = response_from_faqs.answer if response_from_faqs else None

        if not response_content:
            print("No response found from FAQ")
            # Hybrid retrieval
            context_texts, scores = hybrid_retrieval(user_msg, bot_id)

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

            active_tool = db.query(ToolsUsed).filter_by(status=True).first()

            if any(score > 0.6 for score in scores):
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

            user_message = ChatMessage(
                bot_id=bot_id, chat_id=chat.id, sender="user", message=user_msg
            )
            bot_message = ChatMessage(
                bot_id=bot_id, chat_id=chat.id, sender="bot", message=response_content
            )

            db.add_all([user_message, bot_message])
            db.commit()
            db.refresh(bot_message)

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
                consumed_token_type=f"{platform}_bot",
                bot_id=bot_id,
                db=db,
            )
            return response_content

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + (
            expires_delta
            if expires_delta
            else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


def decode_access_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No access token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        # orm
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if user is None:
            raise credentials_exception
        # user['id'] = str(user.id)
        return user
    except JWTError:
        raise credentials_exception


def create_reset_token(data: dict, expires_delta: Optional[timedelta] = None):
    try:
        to_encode = data.copy()
        expire = datetime.utcnow() + (
            expires_delta
            if expires_delta
            else timedelta(minutes=RESET_PASSWORD_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    except JWTError as jwt_exc:
        raise HTTPException(status_code=500, detail="Token creation error") from jwt_exc
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while creating the token",
        ) from e


def decode_reset_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


def send_reset_email(email: str, token: str):
    try:
        reset_link = f"http://localhost:3000/reset-password?token={token}"
        message = MIMEText(f"Click the link to reset your password: {reset_link}")
        message["Subject"] = "Password Reset"
        message["From"] = "no-reply@yourdomain.com"
        message["To"] = email

        # Send email (ensure you configure your SMTP server details)
        with smtplib.SMTP("smtp.yourdomain.com", 587) as server:
            server.starttls()
            server.login("your-email@yourdomain.com", "your-email-password")
            server.sendmail("no-reply@yourdomain.com", email, message.as_string())

    except smtplib.SMTPException as smtp_exc:
        raise HTTPException(
            status_code=500, detail="Failed to send reset email"
        ) from smtp_exc
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while sending the email",
        ) from e


async def get_country_from_ip(ip: str):
    try:
        if ip.startswith("127.") or ip == "localhost":  # fallback for testing
            ip = "8.8.8.8"  # USD
            # ip = "117.197.0.0"  # INR

        url = f"https://ipinfo.io/{ip}/json"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return data.get("country", "Unknown")
        return "Unknown"
    except Exception as e:
        print("IP API error", e)
        return "Unknown"


async def get_paypal_access_token(
    client_id: str, client_secret: str, sandbox: bool = True
) -> str:
    url = (
        "https://api.sandbox.paypal.com/v1/oauth2/token"
        if sandbox
        else "https://api.paypal.com/v1/oauth2/token"
    )

    auth = b64encode(f"{client_id}:{client_secret}".encode()).decode()

    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {"grant_type": "client_credentials"}

    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, data=data)

    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        raise Exception(
            f"Failed to get PayPal access token: {response.status_code} - {response.text}"
        )
