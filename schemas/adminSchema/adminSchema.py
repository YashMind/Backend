from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import timedelta, datetime
class PlansSchema(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    pricing: Optional[int] = None
    token_limits: Optional[int] = False
    features: Optional[str] = None
    users_active: Optional[int] = None

class TokenBotsSchema(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    pricing: Optional[int] = None
    token_limits: Optional[int] = None
    active: Optional[bool] = None

class BotProductSchema(BaseModel):
    id: Optional[int] = None
    product_name: Optional[str] = None
    active: Optional[bool] = None

class PaymentGatewaySchema(BaseModel):
    id: Optional[int] = None
    payment_name: Optional[str] = None
    status: Optional[str] = None
    api_key: Optional[str] = None