from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session

from config import get_db
from utils.utils import decode_access_token
from models.authModel.authModel import AuthUser
from models.chatModel.chatModel import ChatBots, ChatBotsDocLinks, ChatBotsFaqs
from models.chatModel.sharing import ChatBotSharing


router = APIRouter()


@router.get('/data-overview')
async def fetch_user_data_overview(request: Request, db: Session = Depends(get_db)):
  """Return a JSON summary for the current user:
  - user basic info
  - owned chatbots with their doc links and total chars
  - team members (chatbot sharing owned by the user)
  - chatbots shared with the user (and owner info)
  """
  # get token
  token = request.cookies.get("access_token")
  if not token:
    raise HTTPException(status_code=401, detail="Authentication required")

  try:
    payload = decode_access_token(token)
    user_id = int(payload.get("user_id"))
  except HTTPException:
    raise
  except Exception:
    raise HTTPException(status_code=401, detail="Invalid or expired token")

  # fetch user
  user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
  if not user:
    raise HTTPException(status_code=404, detail="User not found")

  # fetch owned chatbots
  owned_bots = db.query(ChatBots).filter(ChatBots.user_id == user_id).all()
  owned_bots_data = []
  for bot in owned_bots:
    links = (
      db.query(ChatBotsDocLinks).filter(ChatBotsDocLinks.bot_id == bot.id).all()
    )
    links_serialized = []
    total_chars = 0
    for l in links:
      links_serialized.append(
        {
          "id": l.id,
          "document_link": l.document_link,
          "target_link": l.target_link,
          "status": l.status,
          "chars": l.chars,
          "created_at": l.created_at.isoformat() if l.created_at else None,
        }
      )
      total_chars += l.chars or 0

    # include bot.text_content chars
    try:
      if getattr(bot, "text_content", None):
        total_chars += len(bot.text_content.strip())
    except Exception:
      # defensive: if text_content is not a string
      pass

    # include chars from FAQs (question + answer lengths)
    faqs = db.query(ChatBotsFaqs).filter(ChatBotsFaqs.bot_id == bot.id).all()
    for faq in faqs:
      q = faq.question.strip() if faq.question else ""
      a = faq.answer.strip() if faq.answer else ""
      total_chars += len(q) + len(a)

    bot_data = bot.as_dict() if hasattr(bot, "as_dict") else {
      "id": bot.id,
      "chatbot_name": getattr(bot, "chatbot_name", None),
    }
    bot_data.update({"doc_links": links_serialized, "total_chars": total_chars})
    owned_bots_data.append(bot_data)

  # fetch team members for bots owned by this user
  team_shares = (
    db.query(ChatBotSharing)
    .filter(ChatBotSharing.owner_id == user_id, ChatBotSharing.status == "active")
    .all()
  )
  team_members = []
  for s in team_shares:
    team_members.append(
      {
        "id": s.id,
        "bot_id": s.bot_id,
        "shared_user_id": s.shared_user_id,
        "shared_email": s.shared_email,
        "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
      }
    )

  # fetch chatbots shared with the user
  shared_with_user = (
    db.query(ChatBotSharing)
    .filter(ChatBotSharing.shared_user_id == user_id, ChatBotSharing.status == "active")
    .all()
  )
  shared_bots = []
  for sh in shared_with_user:
    bot = db.query(ChatBots).filter(ChatBots.id == sh.bot_id).first()
    owner = db.query(AuthUser).filter(AuthUser.id == sh.owner_id).first()
    shared_bots.append(
      {
        "sharing": {
          "id": sh.id,
          "status": sh.status,
          "created_at": sh.created_at.isoformat() if sh.created_at else None,
        },
        "bot": bot.as_dict() if bot and hasattr(bot, "as_dict") else None,
        "owner": {
          "id": owner.id,
          "fullName": owner.fullName,
          "email": owner.email,
        }
        if owner
        else None,
      }
    )

  result = {
    "user": {
      "id": user.id,
      "fullName": user.fullName,
      "email": user.email,
      "role": user.role,
      "plan": user.plan,
    },
    "owned_bots": owned_bots_data,
    "team_members": team_members,
    "shared_bots": shared_bots,
  }

  return result