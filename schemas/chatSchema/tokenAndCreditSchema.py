from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime


class TokenUsageOut(BaseModel):
    id: int
    bot_id: int
    token_limit: Optional[int]
    combined_token_consumption: Optional[int]
    open_ai_request_token: int
    open_ai_response_token: int
    user_request_token: int
    user_response_token: int
    whatsapp_request_tokens: int
    whatsapp_response_tokens: int
    slack_request_tokens: int
    slack_response_tokens: int
    wordpress_request_tokens: int
    wordpress_response_tokens: int
    zapier_request_tokens: int
    zapier_response_tokens: int
    message_limit: Optional[int]
    combined_message_consumption: Optional[int]

    class Config:
        orm_mode = True


class UserCreditsOut(BaseModel):
    id: int
    user_id: int
    trans_id: Optional[int]
    plan_id: Optional[int]
    start_date: datetime
    expiry_date: datetime
    credits_purchased: int
    credits_consumed: int
    credit_balance: int
    token_per_unit: float
    chatbots_allowed: int
    message_per_unit: int
    credits_consumed_messages: int
    credit_balance_messages: int

    class Config:
        orm_mode = True


class ChatMessageTokens(BaseModel):
    credits: Optional[UserCreditsOut]
    token_usage: List[TokenUsageOut]


from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional


# Schemas for UserCredits
class UserCreditBase(BaseModel):
    user_id: int
    trans_id: int
    plan_id: int
    start_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    credits_purchased: int
    credits_consumed: int = 0
    credit_balance: int
    token_per_unit: float
    chatbots_allowed: int
    message_per_unit: int
    credits_consumed_messages: int = 0
    credit_balance_messages: int

class UserCreditCreate(UserCreditBase):
    pass


class UserCreditResponse(UserCreditBase):
    id: int

    class Config:
        orm_mode = True


# Schemas for HistoryUserCredits
class HistoryUserCreditResponse(UserCreditBase):
    id: int
    expiry_reason: Optional[str] = None

    class Config:
        orm_mode = True


# Schemas for TokenUsage
class TokenUsageBase(BaseModel):
    bot_id: int
    user_id: int
    user_credit_id: int
    token_limit: int
    combined_token_consumption: int
    open_ai_request_token: int = 0
    open_ai_response_token: int = 0
    user_request_token: int = 0
    user_response_token: int = 0
    whatsapp_request_tokens: int = 0
    whatsapp_response_tokens: int = 0
    slack_request_tokens: int = 0
    slack_response_tokens: int = 0
    wordpress_request_tokens: int = 0
    wordpress_response_tokens: int = 0
    zapier_request_tokens: int = 0
    zapier_response_tokens: int = 0
    message_limit: int
    combined_message_consumption: int


class TokenUsageCreate(TokenUsageBase):
    pass


class TokenUsageResponse(TokenUsageBase):
    id: int

    class Config:
        orm_mode = True


# Combined response model
class UserCreditsAndTokenUsageResponse(BaseModel):
    credits: Optional[UserCreditResponse] = None
    token_usage: List[TokenUsageResponse] = []
    history_credits: List[HistoryUserCreditResponse] = []
