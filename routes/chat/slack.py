from fastapi import FastAPI, Request, Header, HTTPException, APIRouter, Form, Depends
from fastapi.responses import Response, HTMLResponse
from slack_sdk.web import WebClient
from slack_sdk.signature import SignatureVerifier
import asyncio
from sqlalchemy.orm import Session
from config import Settings, get_db
import httpx
from datetime import datetime
from models.chatModel.integrations import SlackInstallation
from datetime import datetime

router = APIRouter()

# Slack credentials
SLACK_BOT_TOKEN = Settings.SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET = Settings.SLACK_SIGNING_SECRET

SLACK_CLIENT_ID = Settings.SLACK_CLIENT_ID
SLACK_CLIENT_SECRET = Settings.SLACK_CLIENT_SECRET
SLACK_REDIRECT_URI = "https://20d2-122-176-88-30.ngrok-free.app/api/slack/oauth/callback"

client = WebClient(token=SLACK_BOT_TOKEN)
verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

@router.post("/events")
async def slack_events(request: Request,
                       x_slack_signature: str = Header(None),
                       x_slack_request_timestamp: str = Header(None)):
    body = await request.body()
    headers = {
        "X-Slack-Signature": x_slack_signature,
        "X-Slack-Request-Timestamp": x_slack_request_timestamp
    }

    if not verifier.is_valid_request(body, headers):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    event_data = await request.json()
    
    

    # URL verification challenge from Slack
    if "challenge" in event_data:
        return {"challenge": event_data["challenge"]}

    if "event" in event_data:
        event = event_data["event"]
        text = event.get("text", "")
        user = event.get("user")
        channel = event.get("channel")
        print("EVENT TYPE: ",event.get('type'), event.get('subtype'))
        if event.get("subtype") == "bot_message" or event.get("bot_id"):
            return {"ok": True}
        if event.get("type") in ["app_mention", "message"]:
            # Optional filtering for DMs only if needed:
            if event.get("channel_type") in ["im", "channel"]:
                # response = your_ai_bot_logic(text)
                await asyncio.to_thread(client.chat_postMessage, channel=channel, text="this is testing from events")

    return {"ok": True}
    
    
# handle slack commands
@router.post("/commands")
async def slack_commands(
    command: str = Form(...),
    text: str = Form(...),
    user_id: str = Form(...),
    response_url: str = Form(...)
):
    if command == "/yashraa":
        # response = your_ai_bot_logic(text)
        response = f"You said: {text}"

        # Respond to the user asynchronously
        async with httpx.AsyncClient() as client_http:
            await client_http.post(response_url, json={"text": response})

    # Return 200 OK immediately with no message body
    return Response(status_code=204)


async def save_installation(data: dict, db: Session):
    try:
        existing = db.query(SlackInstallation).filter_by(team_id=data["team_id"]).first()

        if existing:
            # Update existing install if needed
            existing.access_token = data["access_token"]
            existing.bot_id = data["bot_id"]
            existing.installed_at = datetime.utcnow()
        else:
            install = SlackInstallation(**data)
            db.add(install)

        db.commit()
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str = "", db: Session = Depends(get_db)):
    # Parse bot_id or other values from state
    # Example: state="bot_id=abc123"
    from urllib.parse import parse_qs
    parsed_state = parse_qs(state)
    bot_id = parsed_state.get("bot_id", [None])[0]

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": SLACK_CLIENT_ID,
                "client_secret": SLACK_CLIENT_SECRET,
                "code": code,
                "redirect_uri": SLACK_REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    token_data = response.json()
    if not token_data.get("ok"):
        raise HTTPException(status_code=400, detail=f"OAuth failed: {token_data.get('error')}")

    # Save to DB
    await save_installation({
        "bot_id": bot_id,
        "access_token": token_data["access_token"],
        "team_id": token_data["team"]["id"],
        "team_name": token_data["team"]["name"],
        "bot_user_id": token_data["bot_user_id"],
        "authed_user_id": token_data["authed_user"]["id"],
        "installed_at": datetime.utcnow()
    },db=db)

    return HTMLResponse("<h3>✅ Slack bot installed successfully!</h3>")
