from typing import List
from pydantic import BaseModel
from datetime import datetime


class TokenUsageSchema(BaseModel):
    id: int
    bot_id: int
    user_id: int
    user_credit_id: int
    token_limit: int
    combined_token_consumption: int
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
    message_limit: int
    combined_message_consumption: int

    class Config:
        from_attributes = True
        orm_mode = True


class UserCreditsSchema(BaseModel):
    id: int
    user_id: int
    trans_id: int
    plan_id: int
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
        from_attributes = True
        orm_mode = True


class ChatMessageTokens(BaseModel):
    credits: UserCreditsSchema
    token_usage: List[TokenUsageSchema]
    total_token_consumption: int
    total_message_consumption: int


class ChatMessageTokensToday(BaseModel):
    request_tokens: int
    response_tokens: int
    users: int
    request_messages: int
    response_messages: int


class ChatMessageTokensSummary(BaseModel):
    today: ChatMessageTokensToday
    monthly: ChatMessageTokensToday
