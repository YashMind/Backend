from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PaymentOrderRequest(BaseModel):
    order_id: str = Field(..., description="Your unique order ID")
    order_amount: float = Field(..., description="Order amount")
    customer_name: str = Field(..., description="Customer full name")
    customer_phone: str = Field(..., description="Customer phone number")
    customer_email: str = Field(..., description="Customer email")
    return_url: str = Field(..., description="URL to redirect after payment")
    notify_url: Optional[str] = Field(None, description="Webhook URL for payment notifications")

class PaymentVerificationRequest(BaseModel):
    order_id: str
    payment_id: Optional[str] = None