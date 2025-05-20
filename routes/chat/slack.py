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
from utils.utils import get_response_from_chatbot
from decorators.product_status import check_product_status

router = APIRouter()

# Slack credentials
SLACK_BOT_TOKEN = Settings.SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET = Settings.SLACK_SIGNING_SECRET

SLACK_CLIENT_ID = Settings.SLACK_CLIENT_ID
SLACK_CLIENT_SECRET = Settings.SLACK_CLIENT_SECRET
SLACK_REDIRECT_URI = Settings.SLACK_REDIRECT_URI

client = WebClient(token=SLACK_BOT_TOKEN)
verifier = SignatureVerifier(SLACK_SIGNING_SECRET)

@router.post("/events")
@check_product_status("chatbot")
async def slack_events(request: Request,
                       x_slack_signature: str = Header(None),
                       x_slack_request_timestamp: str = Header(None),
                       db: Session = Depends(get_db)):
    try:
        print("Start processing Slack event")
        body = await request.body()
        print(f"Raw body: {body}")

        headers = {
            "X-Slack-Signature": x_slack_signature,
            "X-Slack-Request-Timestamp": x_slack_request_timestamp
        }
        print(f"Headers received: {headers}")

        print("Verifying Slack request")
        if not verifier.is_valid_request(body, headers):
            print("Slack signature invalid")
            await asyncio.to_thread(client.chat_postMessage, channel="general", text="Invalid Slack signature")  # Replace 'channel' with a valid fallback
            raise HTTPException(status_code=403, detail="Invalid Slack signature")

        print("Parsing event JSON")
        event_data = await request.json()
        print(f"Event data: {event_data}")

        # URL verification challenge from Slack
        if "challenge" in event_data:
            print("Received challenge")
            return {"challenge": event_data["challenge"]}

        if "event" in event_data:
            print("Processing event block")
            event = event_data["event"]
            text = event.get("text", "")
            user = event.get("user")
            team_id = event_data.get("team_id")
            print(f"Event type: {event.get('type')}, User: {user}, Team ID: {team_id}, Text: {text}")

            bot_installation = db.query(SlackInstallation).filter_by(team_id=team_id).first()
            print(f"Bot installation found: {bot_installation is not None}")

            if not bot_installation:
                print("Bot installation not found")
                await asyncio.to_thread(client.chat_postMessage, channel="general", text="Bot not found for this team")  # Fallback channel
                raise HTTPException(status_code=404, detail="Bot not found for this team")

            channel = event.get("channel")
            print(f"Channel: {channel}")

            if event.get("subtype") == "bot_message" or event.get("bot_id"):
                print("Skipping bot message")
                return {"ok": True}

            if event.get("type") in ["app_mention", "message"]:
                if event.get("channel_type") in ["im", "channel"]:
                    try:
                        print("Generating chatbot response")
                        response = get_response_from_chatbot(
                            data={'message': text, 'bot_id': bot_installation.bot_id, 'token': team_id},
                            platform="slack",
                            db=db
                        )
                        print(f"Response from chatbot: {response}")
                    except Exception as e:
                        print("Error while generating response:", e)
                        await asyncio.to_thread(client.chat_postMessage, channel=channel, text=str(e))
                        raise
                    await asyncio.to_thread(client.chat_postMessage, channel=channel, text=response)

        print("Event processed successfully")
        return {"ok": True}
    except HTTPException as http_exc:
        print(f"HTTPException: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        print(f"Unhandled exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    
    
# handle slack commands
@router.post("/commands")
@check_product_status("chatbot")
async def slack_commands(
    command: str = Form(...),
    text: str = Form(...),
    user_id: str = Form(...),
    response_url: str = Form(...),
    team_id: str = Form(...),
    db : Session = Depends(get_db)
):
    try:
        bot_installation = db.query(SlackInstallation).filter_by(team_id=team_id).first()
        if not bot_installation:
            raise HTTPException(status_code=404, detail="Bot not found for this team")
        
        if command == "/ask_yashraa":
            response = get_response_from_chatbot(data={'message':text,'bot_id':bot_installation.bot_id, 'token':team_id},platform="slack", db=db)

            # Respond to the user asynchronously
            async with httpx.AsyncClient() as client_http:
                await client_http.post(response_url, json={"text": response})

        # Return 200 OK immediately with no message body
        return Response(status_code=204)
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
@check_product_status("chatbot")
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
