import json
import logging
import secrets
from typing import Optional
from fastapi import (
    Query,
    Request,
    HTTPException,
    APIRouter,
    Depends,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse, Response
from slack_sdk.web import WebClient
from slack_sdk.signature import SignatureVerifier
from slack_sdk.errors import SlackApiError
import asyncio
from sqlalchemy.orm import Session
from config import Settings, get_db
from datetime import datetime
from models.authModel.authModel import AuthUser
from models.chatModel.chatModel import ChatBots
from models.chatModel.integrations import SlackInstallation
from datetime import datetime
from utils.encryption import decrypt_data, encrypt_data
from utils.utils import decode_access_token, get_response_from_chatbot
from decorators.product_status import check_product_status
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class SlackRegisterRequest(BaseModel):
    bot_id: str
    client_id: str
    client_secret: str
    signing_secret: str


class SlackUpdateRequest(BaseModel):
    client_secret: Optional[str] = None
    signing_secret: Optional[str] = None
    is_active: Optional[bool] = None


class SlackCredentialsRequest(BaseModel):
    bot_id: str
    client_id: str
    client_secret: str
    signing_secret: str


class SlackOAuthStartRequest(BaseModel):
    bot_id: str
    client_id: str


class SlackUpdateRequest(BaseModel):
    client_secret: Optional[str] = None
    signing_secret: Optional[str] = None
    is_active: Optional[bool] = None


@router.post("/save-credentials", status_code=status.HTTP_201_CREATED)
@check_product_status("chatbot")
async def save_slack_credentials(
    request: Request,
    request_data: SlackCredentialsRequest,
    db: Session = Depends(get_db),
):
    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    # Verify user owns the bot
    if not user_owns_bot(user_id, request_data.bot_id, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    # Encrypt sensitive data
    encrypted_client_secret = encrypt_data(request_data.client_secret)
    encrypted_signing_secret = encrypt_data(request_data.signing_secret)

    # Create or update credentials
    existing = (
        db.query(SlackInstallation)
        .filter_by(bot_id=request_data.bot_id, client_id=request_data.client_id)
        .first()
    )

    if existing:
        existing.client_secret = encrypted_client_secret
        existing.signing_secret = encrypted_signing_secret
        existing.is_active = False  # Needs re-authentication
    else:
        new_credentials = SlackInstallation(
            bot_id=request_data.bot_id,
            client_id=request_data.client_id,
            client_secret=encrypted_client_secret,
            signing_secret=encrypted_signing_secret,
            is_active=False,
        )
        db.add(new_credentials)

    db.commit()
    return {"status": "success", "message": "Slack credentials saved"}


@router.get("/oauth/start")
@check_product_status("chatbot")
async def start_slack_oauth(
    bot_id: str = Query(...), client_id: str = Query(...), db: Session = Depends(get_db)
):
    # Verify credentials exist
    installation = (
        db.query(SlackInstallation)
        .filter_by(bot_id=bot_id, client_id=client_id)
        .first()
    )

    if not installation:
        raise HTTPException(status_code=404, detail="Credentials not found")

    # Generate state token (bot_id + random string)
    state = f"{bot_id}_{secrets.token_urlsafe(16)}"

    # Save state to database
    installation.oauth_state = state
    db.commit()

    # Build OAuth URL
    scopes = [
        "app_mentions:read",
        "channels:history",
        "chat:write",
        "commands",
        "groups:history",
        "im:history",
    ]

    redirect_uri = f"{Settings.BASE_URL}/api/slack/oauth/callback"
    oauth_url = (
        f"https://slack.com/oauth/v2/authorize?"
        f"client_id={installation.client_id}&"
        f"scope={','.join(scopes)}&"
        f"redirect_uri={redirect_uri}&"
        f"state={state}"
    )

    return RedirectResponse(oauth_url)
    # return oauth_url


@router.get("/oauth/callback")
@check_product_status("chatbot")
async def slack_oauth_callback(
    code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)
):
    # Parse bot_id from state
    try:
        bot_id, state_token = state.split("_", 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    # Verify state token
    installation = (
        db.query(SlackInstallation).filter_by(bot_id=bot_id, oauth_state=state).first()
    )

    if not installation:
        raise HTTPException(status_code=404, detail="Invalid state token")

    # Exchange code for access token
    try:
        client = WebClient()
        response = client.oauth_v2_access(
            client_id=installation.client_id,
            client_secret=decrypt_data(installation.client_secret),
            code=code,
            redirect_uri=f"{Settings.BASE_URL}/api/slack/oauth/callback",
        )

        # Save installation details
        installation.access_token = encrypt_data(response["access_token"])
        installation.team_id = response["team"]["id"]
        installation.team_name = response["team"]["name"]
        installation.bot_user_id = response["bot_user_id"]
        installation.authed_user_id = response["authed_user"]["id"]
        installation.installed_at = datetime.utcnow()
        installation.is_active = True
        installation.oauth_state = None  # Clear state after use

        db.commit()

        return RedirectResponse(f"/chatbot-dashboard/integration/{bot_id}")

    except SlackApiError as e:
        raise HTTPException(
            status_code=400, detail=f"Slack OAuth error: {e.response['error']}"
        )


@router.post("/events")
@check_product_status("chatbot")
async def slack_events(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    body_text = body.decode("utf-8")
    event_data = json.loads(body_text)

    # Handle URL verification challenge
    if "challenge" in event_data:
        return {"challenge": event_data["challenge"]}

    # Get team ID from event payload
    team_id = event_data.get("team_id")
    if not team_id:
        return Response(status_code=400)

    # Retrieve installation
    installation = (
        db.query(SlackInstallation).filter_by(team_id=team_id, is_active=True).first()
    )

    if not installation:
        return Response(status_code=404)

    # Verify signature using installation's secret
    try:
        signing_secret = decrypt_data(installation.signing_secret)
        verifier = SignatureVerifier(signing_secret)

        headers = {
            "X-Slack-Signature": request.headers.get("X-Slack-Signature"),
            "X-Slack-Request-Timestamp": request.headers.get(
                "X-Slack-Request-Timestamp"
            ),
        }

        if not verifier.is_valid_request(body, headers):
            return Response(status_code=403)
    except Exception as e:
        return Response(status_code=500, content=str(e))

    # Process event
    if "event" in event_data:
        event = event_data["event"]
        if event.get("type") in ["app_mention", "message"]:
            await handle_slack_message(event, installation, db)

    return {"ok": True}


async def handle_slack_message(event, installation, db):
    text = event.get("text", "")
    channel = event.get("channel")
    user = event.get("user")

    if event.get("bot_id") or not text:
        return

    # Get decrypted access token
    access_token = decrypt_data(installation.access_token)
    client = WebClient(token=access_token)

    # Get chatbot response
    try:
        response = get_response_from_chatbot(
            data={
                "message": text,
                "bot_id": installation.bot_id,
                "token": installation.team_id,
            },
            platform="slack",
            db=db,
        )

        # Send response
        await asyncio.to_thread(client.chat_postMessage, channel=channel, text=response)

        # Update last used timestamp
        installation.last_used = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.error(f"Error handling Slack message: {str(e)}")


@router.post("/commands")
@check_product_status("chatbot")
async def slack_commands(request: Request, db: Session = Depends(get_db)):
    form_data = await request.form()
    team_id = form_data.get("team_id")

    print(form_data)

    if not team_id:
        return Response(status_code=400)

    # Retrieve installation
    installation = (
        db.query(SlackInstallation).filter_by(team_id=team_id, is_active=True).first()
    )

    if not installation:
        return Response(status_code=404)

    # Get decrypted access token
    access_token = decrypt_data(installation.access_token)
    client = WebClient(token=access_token)

    # Handle command
    command = form_data.get("command")
    text = form_data.get("text")
    user_id = form_data.get("user_id")
    channel_id = form_data.get("channel_id")

    if command == "/ask":
        try:
            response = get_response_from_chatbot(
                data={
                    "message": text,
                    "bot_id": installation.bot_id,
                    "token": installation.team_id,
                },
                platform="slack",
                db=db,
            )

            await asyncio.to_thread(
                client.chat_postMessage, channel=channel_id, text=response
            )
        except Exception as e:
            logger.error(f"Error handling Slack command: {str(e)}")

    return Response(status_code=200)


@router.get("/installation/{bot_id}")
async def get_slack_installation(
    bot_id: str, request: Request, db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    if not user_owns_bot(user_id, bot_id, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    installation = db.query(SlackInstallation).filter_by(bot_id=bot_id).first()
    return {
        "id": installation.id,
        "client_id": installation.client_id,
        "team_id": installation.team_id,
        "team_name": installation.team_name,
        "installed_at": installation.installed_at,
        "is_active": installation.is_active,
        "last_used": installation.last_used,
    }


@router.put("/installation/{installation_id}")
async def update_slack_installation(
    installation_id: int,
    request_data: SlackUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    installation = db.query(SlackInstallation).filter_by(id=installation_id).first()
    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")

    if not user_owns_bot(user_id, installation.bot_id, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    if request_data.client_secret:
        installation.client_secret = encrypt_data(request_data.client_secret)

    if request_data.signing_secret:
        installation.signing_secret = encrypt_data(request_data.signing_secret)

    if request_data.is_active is not None:
        installation.is_active = request_data.is_active

    db.commit()
    return {"status": "success"}


@router.delete("/installation/{bot_id}")
async def delete_slack_installation(
    bot_id: int, request: Request, db: Session = Depends(get_db)
):
    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))

    installation = db.query(SlackInstallation).filter_by(bot_id=bot_id).first()
    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")

    if not user_owns_bot(user_id, installation.bot_id, db):
        raise HTTPException(status_code=403, detail="Unauthorized")

    db.delete(installation)
    db.commit()
    return {"status": "success"}


def user_owns_bot(user_id: int, bot_id: int, db: Session) -> bool:
    # Replace with actual logic to verify bot ownership
    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if not user:
        return False
    bot = (
        db.query(ChatBots)
        .filter(ChatBots.id == bot_id, ChatBots.user_id == user_id)
        .first()
    )
    if not bot:
        return False

    return True  # Example


# async def save_installation(data: dict, db: Session):
#     try:
#         existing = (
#             db.query(SlackInstallation).filter_by(team_id=data["team_id"]).first()
#         )

#         if existing:
#             # Update existing install if needed
#             existing.access_token = data["access_token"]
#             existing.bot_id = data["bot_id"]
#             existing.installed_at = datetime.utcnow()
#         else:
#             install = SlackInstallation(**data)
#             db.add(install)

#         db.commit()
#     except HTTPException as http_exc:
#         raise http_exc
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# @router.get("/oauth/callback")
# @check_product_status("chatbot")
# async def oauth_callback(code: str, state: str = "", db: Session = Depends(get_db)):
#     # Parse bot_id or other values from state
#     # Example: state="bot_id=abc123"
#     from urllib.parse import parse_qs

#     parsed_state = parse_qs(state)
#     bot_id = parsed_state.get("bot_id", [None])[0]

#     # Exchange code for token
#     async with httpx.AsyncClient() as client:
#         response = await client.post(
#             "https://slack.com/api/oauth.v2.access",
#             data={
#                 "client_id": SLACK_CLIENT_ID,
#                 "client_secret": SLACK_CLIENT_SECRET,
#                 "code": code,
#                 "redirect_uri": SLACK_REDIRECT_URI,
#             },
#             headers={"Content-Type": "application/x-www-form-urlencoded"},
#         )

#     token_data = response.json()
#     if not token_data.get("ok"):
#         raise HTTPException(
#             status_code=400, detail=f"OAuth failed: {token_data.get('error')}"
#         )

#     # Save to DB
#     await save_installation(
#         {
#             "bot_id": bot_id,
#             "access_token": token_data["access_token"],
#             "team_id": token_data["team"]["id"],
#             "team_name": token_data["team"]["name"],
#             "bot_user_id": token_data["bot_user_id"],
#             "authed_user_id": token_data["authed_user"]["id"],
#             "installed_at": datetime.utcnow(),
#         },
#         db=db,
#     )

#     return HTMLResponse("<h3>✅ Slack bot installed successfully!</h3>")


# @router.post("/register", status_code=status.HTTP_201_CREATED)
# @check_product_status("chatbot")
# async def register_slack_app(
#     request: Request, request_data: SlackRegisterRequest, db: Session = Depends(get_db)
# ):
#     token = request.cookies.get("access_token")
#     payload = decode_access_token(token)
#     user_id = int(payload.get("user_id"))

#     # Verify user owns the bot
#     if not user_owns_bot(user_id, request_data.bot_id, db):
#         raise HTTPException(status_code=403, detail="Unauthorized")

#     # Verify Slack credentials
#     auth_test = None
#     team_id = None
#     try:
#         test_client = WebClient()
#         auth_test = test_client.oauth_v2_access(
#             client_id=request_data.client_id, client_secret=request_data.client_secret
#         )
#         team_id = auth_test["team_id"]
#     except SlackApiError as e:
#         raise HTTPException(
#             status_code=400, detail=f"Invalid Slack credentials: {e.response['error']}"
#         )

#     # Encrypt sensitive data
#     encrypted_client_secret = encrypt_data(request_data.client_secret)
#     encrypted_signing_secret = encrypt_data(request_data.signing_secret)

#     # Create or update installation
#     existing = (
#         db.query(SlackInstallation)
#         .filter_by(bot_id=request_data.bot_id, team_id=team_id)
#         .first()
#     )

#     if existing:
#         existing.client_secret = encrypted_client_secret
#         existing.signing_secret = encrypted_signing_secret
#         existing.is_active = True
#     else:
#         new_install = SlackInstallation(
#             bot_id=request_data.bot_id,
#             team_id=team_id,
#             team_name=auth_test["team"],
#             bot_user_id=auth_test["bot_id"],
#             authed_user_id=auth_test["user_id"],
#             access_token=encrypt_data(auth_test["bot_access_token"]),
#             client_id=request_data.client_id,
#             client_secret=encrypted_client_secret,
#             signing_secret=encrypted_signing_secret,
#         )
#         db.add(new_install)

#     db.commit()
#     return {"status": "success", "message": "Slack app registered"}
