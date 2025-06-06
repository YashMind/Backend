from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PaymentOrderRequest(BaseModel):
    customer_id: int = Field(..., description="Your unique customer ID")
    plan_id: int = Field(..., description="Customer chosen plan ID")
    credit: int = Field(
        ..., description="Amount of credit to add to the customer's account"
    )
    return_url: str = Field(..., description="URL to redirect after payment")


class PaymentVerificationRequest(BaseModel):
    order_id: str
    payment_id: Optional[str] = None
