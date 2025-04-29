from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Pydantic Models
class InstructionPromptBase(BaseModel):
    id: Optional[int] = None
    type: str
    prompt: str

class InstructionPromptCreate(InstructionPromptBase):
    bot_id: Optional[int] = None

class InstructionPrompt(InstructionPromptCreate):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True

class BotPromptsUpdate(BaseModel):
    bot_id: int
    prompts: List[InstructionPromptBase]