from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import timedelta, datetime
from typing import List


class PostEmail(BaseModel):
    title: str
    description: str
    recipients: List[EmailStr]


class PlansSchema(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    pricingInr: Optional[int] = None
    pricingDollar: Optional[int] = None
    token_per_unit: Optional[int] = False
    chatbots_allowed: Optional[int] = False
    chars_allowed: Optional[int] = False
    webpages_allowed: Optional[int] = False
    team_strength: Optional[int] = False
    duration_days: Optional[int] = False
    features: Optional[str] = None
    users_active: Optional[int] = None
    message_per_unit: Optional[int] = False


class TokenBotsSchema(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    pricing: Optional[int] = None
    token_per_unit: Optional[int] = False
    chatbots_allowed: Optional[int] = False
    duration_days: Optional[int] = False
    active: Optional[bool] = None
    message_per_unit: Optional[int] = False


class BotProductSchema(BaseModel):
    id: Optional[int] = None
    product_name: Optional[str] = None
    active: Optional[bool] = None


class RolePermissionInput(BaseModel):
    role: str
    permissions: List[str]


class RolePermissionResponse(BaseModel):
    role: str
    permissions: List[str]


class PaymentGatewaySchema(BaseModel):
    id: Optional[int] = None
    payment_name: Optional[str] = None
    status: Optional[str] = None
    api_key: Optional[str] = None
