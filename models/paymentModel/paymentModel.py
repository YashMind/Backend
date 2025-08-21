from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime


class PaymentOrderRequest(BaseModel):
    customer_id: int = Field(..., description="Your unique customer ID")
    plan_id: Optional[int] = Field(None, description="Customer chosen plan ID")
    credit: Optional[int] = Field(None, description="Amount of credit to add")
    return_url: str = Field(..., description="URL to redirect after payment")

    @model_validator(mode="after")
    def check_plan_or_credit(self) -> "PaymentOrderRequest":
        if self.plan_id is None and self.credit is None:
            raise ValueError("Either 'plan_id' or 'credit' must be provided.")
        return self


class PaymentVerificationRequest(BaseModel):
    order_id: str
    payment_id: Optional[str] = None
    signature: Optional[str] = None



    