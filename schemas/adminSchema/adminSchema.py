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