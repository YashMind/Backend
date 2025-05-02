from pydantic import BaseModel
from typing import Optional

# Pydantic schemas
class ChatSettingsBase(BaseModel):
    bot_id: int 
    title_value: Optional[str] = None
    title_is_active: Optional[bool]= None
    welcome_message_value: Optional[str] = None
    welcome_message_is_active: Optional[bool]= None
    suggestions_value: Optional[str] = None
    suggestions_is_active: Optional[bool]= None
    placeholder_value: Optional[str] = None
    placeholder_is_active: Optional[bool]= None
    # lead_collection: Optional[bool]= None
    chat_window_bg: Optional[str] = None
    send_button_color: Optional[str] = None
    chat_icon: Optional[str] = None
    chat_icon_color: Optional[str] = None
    user_message_bg: Optional[str] = None
    image: Optional[str] = None
    dots_color: Optional[str] = None
    message_bg: Optional[str] = None
    live_message_bg: Optional[str] = None
    class Config:
        orm_mode = True

class ChatSettingsCreate(ChatSettingsBase):
    pass

class ChatSettingsUpdate(ChatSettingsBase):
    pass

class ChatSettingsRead(ChatSettingsBase):
    id: int
    bot_id:int
    title_value: Optional[str] = None
    title_is_active: Optional[bool]= None
    welcome_message_value: Optional[str] = None
    welcome_message_is_active: Optional[bool]= None
    suggestions_value: Optional[str] = None
    suggestions_is_active: Optional[bool]= None
    placeholder_value: Optional[str] = None
    placeholder_is_active: Optional[bool]= None
    lead_collection: Optional[bool]= None
    chat_window_bg: Optional[str] = None
    send_button_color: Optional[str] = None
    chat_icon: Optional[str] = None
    chat_icon_color: Optional[str] = None
    user_message_bg: Optional[str] = None
    image: Optional[str] = None
    dots_color: Optional[str] = None
    message_bg: Optional[str] = None
    live_message_bg: Optional[str] = None


