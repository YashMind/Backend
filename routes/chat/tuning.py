import json
import os
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from typing import List, Dict
from datetime import datetime
from config import get_db
from models.chatModel.sharing import ChatBotSharing
from models.chatModel.tuning import DBInstructionPrompt
from schemas.chatSchema.tuningSchema import (
    InstructionPrompt,
    BotPromptsUpdate,
    InstructionPromptFetch,
)
from models.chatModel.chatModel import ChatBots
from utils.utils import decode_access_token
from decorators.product_status import check_product_status


router = APIRouter()


@router.post("/prompts", response_model=List[InstructionPrompt])
@check_product_status("chatbot")
async def create_or_update_prompts(
    data: BotPromptsUpdate, request: Request, db: Session = Depends(get_db)
):
    try:
        user_id = get_authenticated_user(request)

        # Validate bot ownership if bot_id is provided
        if data.bot_id:
            bot = db.query(ChatBots).filter(ChatBots.id == data.bot_id).first()
            if not bot or bot.user_id != user_id:
                raise HTTPException(status_code=403, detail="Invalid bot access")

        updated_prompts = []

        for prompt_data in data.prompts:
            existing_prompt = (
                db.query(DBInstructionPrompt)
                .filter(
                    DBInstructionPrompt.bot_id == data.bot_id,
                    DBInstructionPrompt.type == prompt_data.type,
                )
                .first()
            )

            if existing_prompt:
                # Update existing prompt by type
                for key, value in prompt_data.dict().items():
                    if key != "id" and hasattr(existing_prompt, key):
                        setattr(existing_prompt, key, value)
                existing_prompt.updated_at = datetime.utcnow()
                updated_prompts.append(existing_prompt)
            else:
                # Create new prompt if type doesn't exist for this bot
                new_prompt = DBInstructionPrompt(
                    **prompt_data.dict(exclude={"id"}),
                    bot_id=data.bot_id,
                    user_id=user_id,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(new_prompt)
                updated_prompts.append(new_prompt)

        db.commit()

        # Refresh all updated/created prompts
        for prompt in updated_prompts:
            db.refresh(prompt)

        return updated_prompts

    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


# Get Bot Prompts
@router.get("/bots/{bot_id}/prompts", response_model=InstructionPromptFetch)
@check_product_status("chatbot")
async def get_bot_prompts(bot_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        user_id = get_authenticated_user(request)

        # First check if user owns the bot
        owned_bot = (
            db.query(ChatBots)
            .filter(ChatBots.id == bot_id, ChatBots.user_id == user_id)
            .first()
        )

        if owned_bot:
            # User owns the bot, proceed to get prompts
            prompts = (
                db.query(DBInstructionPrompt)
                .filter(DBInstructionPrompt.bot_id == bot_id)
                .all()
            )
            return {"bot_id": bot_id, "prompts": prompts}

        # If user doesn't own the bot, check if it's shared with them
        shared_bot = (
            db.query(ChatBotSharing)
            .join(ChatBots, ChatBots.id == ChatBotSharing.bot_id)
            .filter(
                ChatBotSharing.bot_id == bot_id,
                ChatBotSharing.shared_user_id == user_id,
                ChatBotSharing.status == "active",
            )
            .first()
        )

        if shared_bot:
            # User has access to the shared bot, get the prompts
            prompts = (
                db.query(DBInstructionPrompt)
                .filter(DBInstructionPrompt.bot_id == bot_id)
                .all()
            )
            return {"bot_id": bot_id, "prompts": prompts}

        # If we get here, the user has no access to the bot
        # We don't reveal whether the bot exists or not
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to access this bot's prompts",
        )

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Helper function (implement your auth logic)
def get_authenticated_user(request: Request):
    # Implement your authentication logic
    # Example: JWT decoding from cookies
    token = request.cookies.get("access_token")
    payload = decode_access_token(token)
    return int(payload.get("user_id"))


def seed_instruction_prompts_template(
    user_id: int, bot_id: int, domain: str, db: Session = Depends(get_db)
):
    try:
        file_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "utils", "instruction_prompts.json"
        )

        with open(file_path, "r", encoding="utf-8") as f:
            prompt_data = json.load(f)

        # Find the prompt that matches the given domain (label)
        matching_prompt = None
        for item in prompt_data:
            if item.get("label", "") == domain:
                matching_prompt = item
                break

        if not matching_prompt:
            return False, f"No prompt template found for domain: {domain}"

        # Convert JSON string with \n to actual newlines
        prompt_text = matching_prompt.get("prompt", "").replace("\\n", "\n")

        prompt_entry = DBInstructionPrompt(
            user_id=user_id,
            bot_id=bot_id,
            type=matching_prompt.get("label"),
            prompt=prompt_text,
        )
        db.add(prompt_entry)
        db.commit()

        return True, f"Added Instruction prompt for domain: {domain}"

    except HTTPException as e:
        db.rollback()
        return False, f"Error seeding Instruction prompt: {str(e)}"
    except Exception as e:
        db.rollback()
        return False, f"Error seeding Instruction prompt: {str(e)}"
