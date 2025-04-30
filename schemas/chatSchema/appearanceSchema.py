from pydantic import BaseModel
from typing import Optional

# Pydantic schemas
class ChatSettingsBase(BaseModel):
    class Config:
        orm_mode = True

class ChatSettingsCreate(ChatSettingsBase):
    pass

class ChatSettingsUpdate(ChatSettingsBase):
    pass

class ChatSettingsRead(ChatSettingsBase):
    id: int
    title_value: str | None
    title_is_active: bool | None
    welcome_message_value: str | None
    welcome_message_is_active: bool | None
    suggestions_value: str | None
    suggestions_is_active: bool | None
    placeholder_value: str | None
    placeholder_is_active: bool | None
    lead_collection: bool | None
    send_button_color: str | None
    chat_icon: str | None
    chat_icon_color: str | None
    user_message_bg: str | None
    image: str | None
    dots_color: str | None
    message_bg: str | None
    live_message_bg: str | None


