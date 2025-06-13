import json
import os
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from typing import List, Dict
from datetime import datetime
from config import get_db
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

        bot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()
        if not bot or bot.user_id != user_id:
            raise HTTPException(
                status_code=403, detail="Bot not found or access denied"
            )

        prompts = (
            db.query(DBInstructionPrompt)
            .filter(DBInstructionPrompt.bot_id == bot_id)
            .all()
        )

        print(bot_id, type(bot_id))
        return {"bot_id": bot_id, "prompts": prompts}

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
    user_id: int, bot_id: int, db: Session = Depends(get_db)
):
    try:
        file_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "utils", "instruction_prompts.json"
        )

        with open(file_path, "r", encoding="utf-8") as f:
            prompt_data = json.load(f)

        for item in prompt_data:
            # Convert JSON string with \n to actual newlines
            prompt_text = item.get("prompt", "").replace("\\n", "\n")

            prompt_entry = DBInstructionPrompt(
                user_id=user_id,
                bot_id=bot_id,
                type=item.get("label"),
                prompt=prompt_text,  # Use the converted text
            )
            db.add(prompt_entry)

        db.commit()
        return True, f"Added {len(prompt_data)} Instruction prompts."

    except HTTPException as e:
        return False, f"Error seeding Instruction prompts: {str(e)}"
    except Exception as e:
        return False, f"Error seeding Instruction prompts: {str(e)}"
