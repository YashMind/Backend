from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
from config import get_db
from models.chatModel.tuning import DBInstructionPrompt
from schemas.chatSchema.tuningSchema import InstructionPrompt,BotPromptsUpdate
from models.chatModel.chatModel import ChatBots
from utils.utils import  decode_access_token


router = APIRouter()

@router.post("/prompts", response_model=List[InstructionPrompt])
async def create_or_update_prompts(
    data: BotPromptsUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user_id = get_authenticated_user(request)
        
        # Validate bot ownership if bot_id is provided
        if data.bot_id:
            bot = db.query(ChatBots).filter(ChatBots.id == data.bot_id).first()
            if not bot or bot.user_id != user_id:
                raise HTTPException(status_code=403, detail="Invalid bot access")

        existing_prompts = db.query(DBInstructionPrompt).filter(
            DBInstructionPrompt.bot_id == data.bot_id
        ).all()
        
        existing_prompt_map = {prompt.id: prompt for prompt in existing_prompts}
        
        updated_prompts = []
        
        for prompt_data in data.prompts:
            # If prompt has an ID, check if it exists and belongs to this user/bot
            if hasattr(prompt_data, 'id') and prompt_data.id:
                existing_prompt = existing_prompt_map.get(prompt_data.id)
                if existing_prompt:
                    # Update existing prompt
                    for key, value in prompt_data.dict().items():
                        if key != 'id' and hasattr(existing_prompt, key):
                            setattr(existing_prompt, key, value)
                    existing_prompt.updated_at = datetime.utcnow()
                    updated_prompts.append(existing_prompt)
                    continue
            
            # Create new prompt
            new_prompt = DBInstructionPrompt(
                **prompt_data.dict(exclude={'id'}),  # Exclude id for new prompts
                bot_id=data.bot_id,
                user_id=user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
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
@router.get("/bots/{bot_id}/prompts", response_model=List[InstructionPrompt])
async def get_bot_prompts(
    bot_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user_id = get_authenticated_user(request)
        
        bot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()
        if not bot or bot.user_id != user_id:
            raise HTTPException(status_code=403, detail="Bot not found or access denied")

        return db.query(DBInstructionPrompt).filter(
            DBInstructionPrompt.bot_id == bot_id
        ).all()

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