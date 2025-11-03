from base64 import b64encode
from types import SimpleNamespace
from cachetools import TTLCache
from fastapi import HTTPException, Depends, Request, status
from fastapi.responses import JSONResponse
from datetime import datetime, timedelta
from jose import JWTError, jwt
from typing import Optional
from sqlalchemy.orm import Session
from config import get_db
from models.adminModel.toolsModal import ToolsUsed
from models.chatModel.sharing import ChatBotSharing
from models.chatModel.tuning import DBInstructionPrompt
from routes.chat.pinecone import (
    generate_response,
    get_response_from_faqs,
    hybrid_retrieval,
)
from models.authModel.authModel import AuthUser
from models.chatModel.chatModel import ChatBots, ChatBotsFaqs, ChatSession, ChatMessage
from email.mime.text import MIMEText
import smtplib
import httpx
import re
from html import unescape
from bs4 import BeautifulSoup
from routes.subscriptions.token_usage import (
    update_token_usage_on_consumption,
    verify_token_limit_available,
)
import re
from rapidfuzz import fuzz
from config import get_db, settings


SECRET_KEY = "ADMIN@1234QWER"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 20160  # 2 weeks
RESET_PASSWORD_TOKEN_EXPIRE_MINUTES = 15


def get_recent_chat_history(db: Session, chat_id: str):
    if not chat_id:
        return []

    # Get messages (both user and bot) in one query for efficiency
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.chat_id == chat_id, ChatMessage.sender.in_(["user", "bot"]))
        .order_by(ChatMessage.created_at.desc())
        .limit(6)  # 3 user + 3 bot messages
        .all()
    )

    # Convert to pure Python dictionaries
    history = [
        {
            "sender": msg.sender,
            "message": msg.message,
            "time": msg.created_at.isoformat(),  # ISO 8601 format
        }
        for msg in messages
    ]

    # Sort by time (newest first) just in case
    history.sort(key=lambda x: x["time"], reverse=True)

    return history


async def get_response_from_chatbot(data, platform, db: Session):
    print(f"IN: get_response_from_chatbot from {platform}")
    try:
        user_msg = data.get("message")
        bot_id = data.get("bot_id")
        token = data.get("token")

        if not user_msg:
            raise HTTPException(status_code=400, detail="Message required")

        token_limit_availabe, message = verify_token_limit_available(
            bot_id=bot_id, db=db
        )
        print("Checking Message limit:",token_limit_availabe, message)
        if not token_limit_availabe:
            # raise HTTPException(
            #     status_code=400, detail=f"Token limit exceeded: {message}"
            # )
            print("Message limit exceeded")
            return "Sorry can't reply you at the moment, Message Limit exceeded"

        chatbot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="ChatBot not found")

        chat = db.query(ChatSession).filter_by(token=token).first()
        if not chat:
            chat = ChatSession(token=token, platform=platform, bot_id=bot_id)
            db.add(chat)
            db.commit()

        message_history = get_recent_chat_history(chat_id=chat.id, db=db)

        (
            request_tokens,
            response_tokens,
            openai_request_tokens,
            openai_response_tokens,
        ) = (0, 0, 0, 0)
        response_from_faqs = get_response_from_faqs(user_msg, bot_id, db)

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

            if any(score > 0 for score in scores):
                print("using openai with context")
                use_openai = True
                generated_res = generate_response(
                        query=user_msg,
                        context=context_texts[:3],
                        use_openai=use_openai,
                        instruction_prompts=dict_ins_prompt,
                        creativity=creativity,
                        text_content=text_content,
                        active_tool=active_tool,
                        message_history=message_history,
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
                print("CALLING: generate_response")
                try:
                    generated_res = generate_response(
                        query=user_msg,
                        context=[],
                        use_openai=use_openai,
                        instruction_prompts=dict_ins_prompt,
                        creativity=creativity,
                        text_content=text_content,
                        active_tool=active_tool,
                        message_history=message_history,
                    )
                except Exception as e:
                    print(f"some exception in generate response occur:{e}")
                answer = generated_res[0]
                
                print(f"Answer from generate_response: {answer}")
                openai_request_tokens = generated_res[1]
                openai_response_tokens = generated_res[2]
                request_tokens = generated_res[3]
                print("ANSWER", answer, openai_request_tokens)

            response_content = answer if answer else response_content

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
                request_message=1,
                response_message=1,
            )
            update_token_usage_on_consumption(
                consumed_token=consumed_token,
                consumed_token_type=f"{platform}_bot",
                bot_id=bot_id,
                db=db,
            )
        return html_to_whatsapp_format(response_content)

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def html_to_whatsapp_format(html_text: str) -> str:
    soup = BeautifulSoup(unescape(html_text), "html.parser")

    def convert_node(node, in_list=False, list_type=None, list_index=1):
        if node.name in ["b", "strong"]:
            return f"*{convert_children(node)}*"
        elif node.name in ["i", "em"]:
            return f"_{convert_children(node)}_"
        elif node.name in ["s", "strike", "del"]:
            return f"~{convert_children(node)}~"
        elif node.name in ["code", "pre"]:
            content = node.get_text().strip()
            return f"```\n{content}\n```"
        elif node.name == "br":
            return "\n"
        elif node.name == "p":
            return f"{convert_children(node)}\n\n"
        elif node.name == "ul":
            return (
                "\n".join(
                    convert_node(li, in_list=True, list_type="ul")
                    for li in node.find_all("li", recursive=False)
                )
                + "\n"
            )
        elif node.name == "ol":
            return (
                "\n".join(
                    convert_node(li, in_list=True, list_type="ol", list_index=i + 1)
                    for i, li in enumerate(node.find_all("li", recursive=False))
                )
                + "\n"
            )
        elif node.name == "li":
            prefix = f"{list_index}. " if list_type == "ol" else "• "
            return f"{prefix}{convert_children(node)}"
        elif node.name == "a":
            href = node.get("href")
            text = convert_children(node).strip()
            if href:
                return f"{text} ({href})" if text else href
            return text
        else:
            return convert_children(node)

    def convert_children(parent):
        if not hasattr(parent, "contents"):
            return str(parent)

        result = []
        for child in parent.contents:
            if hasattr(child, "name"):
                result.append(str(convert_node(child)))
            else:
                result.append(str(child))  # plain text (NavigableString)
        return "".join(result)

    # Start processing from the body
    output = convert_children(soup)
    # Cleanup: collapse extra newlines and spaces
    return re.sub(r"\n{3,}", "\n\n", output).strip()


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
        print(str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


def send_reset_email(email: str, token: str):
    try:
        reset_link = f"https://yashraa.ai/auth/reset-password?token={token}"
        message = MIMEText(f"Click the link to reset your password: {reset_link}")
        message["Subject"] = "Password Reset"
        message["From"] = settings.EMAIL_ADDRESS
        message["To"] = email

        # Send email (ensure you configure your SMTP server details)
        with smtplib.SMTP(settings.SMTP_HOST, 587) as server:
            server.starttls()
            server.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
            server.sendmail(settings.EMAIL_ADDRESS, email, message.as_string())

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
            # ip = "8.8.8.8"  # USD
            ip = "117.197.0.0"  # INR

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


async def get_user_country(ip: str, user_id: int = None, db: Session = None):
    """
    Get user's country with priority:
    1. User's saved country preference
    2. IP-based country lookup (and save it)
    """
    # First check if user has country saved
    if db and user_id:
        try:
            user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
            if user and user.country:
                print(f"Using saved country {user.country} for user {user_id}")
                return user.country
        except Exception as e:
            print(f"Error checking user country: {e}")
    
    # Fallback to IP lookup and save
    return await get_country_from_ip(ip)


async def get_timezone_from_ip(ip: str) -> str:
    try:
        if ip.startswith("127.") or ip == "localhost":  # fallback for testing
            # ip = "8.8.8.8"  # America/Los_Angeles
            ip = "117.197.0.0"  # Asia/Kolkata

        url = f"https://ipinfo.io/{ip}/json"
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                return data.get("timezone", "UTC")  # Default to UTC if not found
        return "UTC"
    except Exception as e:
        print("IP API error", e)
        return "UTC"


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
        


def validate_response(response, min_length=10, max_incomplete_penalty=3, fuzzy_threshold=85):
    """
    Validates an AI-generated response with minimal token usage and fuzzy detection for inability phrases.
    
    Args:
        response (str): The AI-generated response to validate
        min_length (int): Minimum acceptable response length in words
        max_incomplete_penalty (int): Max allowed incomplete sentences
        fuzzy_threshold (int): Minimum fuzzy match score to consider an error phrase matched
        
    Returns:
        tuple: (is_valid: bool, reason: str or None)
    """
    # Remove HTML
    clean_response = re.sub(r'<[^>]+>', '', response or "").strip()

    if not clean_response:
        return (False, "Empty response")

    # Word and sentence split
    words = clean_response.split()
    sentences = re.split(r'[.!?]\s+', clean_response)

    # (Optional) check min word length
    # if len(words) < min_length:
    #     return (False, f"Response too short (min {min_length} words required)")

    # Incomplete sentence penalty check
    incomplete_count = 0
    for sentence in sentences[:-1]:  # Last sentence may be legitimately cut off
        if not sentence.strip() or not sentence[-1].isalnum():
            incomplete_count += 1
            if incomplete_count >= max_incomplete_penalty:
                return (False, "Too many incomplete sentences")

    # Fuzzy error phrase detection
    error_phrases = [
        "i don't know",
        "i cannot answer",
        "i'm not sure",
        "i don't have information",
        "i don't understand",
        "i'm unable to",
        "i don't have enough context",
        "i don't have access to",
        "i'm not programmed to",
        "i don't have the capability",
        "apologies",
        "i was trained on data up to",
        "my knowledge is limited",
        "i cannot provide that information",
        "i’m not able to help with that",
        "that’s outside my scope",
        "sorry, i can’t provide that"
    ]

    # Lowercased for matching
    sentences_lower = [s.lower() for s in sentences]

    for sent in sentences_lower:
        for phrase in error_phrases:
            if fuzz.partial_ratio(phrase, sent) >= fuzzy_threshold:
                return (False, "AI indicated inability to answer")

    return (True, None)


def handle_invalid_response(question, user_id, bot_id, db, response=None, reason=None):
    """
    Handles invalid responses by adding to FAQ storage.
    
    Args:
        question (str): The original question
        user_id: User ID
        bot_id: Bot ID
        db: Database session
        response (str, optional): The invalid response
        reason (str, optional): Why the response was invalid
    """
    try:
        
        # First check if this question already exists in FAQs
        existing_faq = db.query(ChatBotsFaqs).filter(
            ChatBotsFaqs.bot_id == bot_id,
            ChatBotsFaqs.question.ilike(f"%{question}%")
        ).first()
        
        if existing_faq:
            return existing_faq

        new_faq = ChatBotsFaqs(
            question=question,
            answer=None,
            user_id=user_id,
            bot_id=bot_id,
        )

        db.add(new_faq)
        db.commit()
        db.refresh(new_faq)
        
        print(f"Saved invalid response to FAQs - Question: {question[:50]}...")
        return new_faq
        
    except Exception as e:
        db.rollback()
        print(f"Error saving to FAQ database: {e}")
        return None


async def verify_chatbot_ownership(user_id:int, bot_id:int, db:Session = Depends(get_db)):
    try:
        bot = db.query(ChatBots).filter(ChatBots.id==bot_id).first()
        if not bot:
            raise HTTPException(status_code=404, detail="bot not found")
        
        user = db.query(AuthUser).filter(AuthUser.id ==user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="bot not found")
        
        if bot.user_id != user.id:
            # check sharing bots
            shared_bot= db.query(ChatBotSharing).filter(ChatBotSharing.shared_user_id==user.id).filter(ChatBotSharing.bot_id == bot_id).first()
            if shared_bot:
                return True, user, bot
            
        else:  
            return True , user, bot
        
        return False, user, bot

    except Exception as e:
        raise HTTPException(status_code=400, detail=e )