from sqlalchemy import (
    Column,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    JSON,
    Integer,
    Enum,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from config import Base


class Transaction(Base):
    __tablename__ = "transactions"

    # Core transaction ID
    id = Column(Integer, primary_key=True, index=True)

    # Relationships
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=True)

    # Transaction Type plan or topup
    transaction_type = Column(Enum("plan", "topup"), nullable=False)

    # Payment essentials
    amount = Column(Numeric(15, 2), nullable=False)  # Supports 999,999,999,999.99
    currency = Column(String(3), default="INR")

    # Provider info
    provider = Column(
        Enum("cashfree", "paypal", "stripe", name="payment_providers"), nullable=False
    )
    provider_transaction_id = Column(String(255))  # Gateway's transaction ID

    # Status tracking (generic states)
    status = Column(
        Enum(
            "created",
            "pending",
            "success",
            "failed",
            "refunded",
            "cancelled",
            name="transaction_status",
        ),
        default="created",
    )

    # Idempotency keys
    order_id = Column(String(100), unique=True)  # Your internal order ID
    provider_payment_id = Column(String(255), unique=True)  # Gateway's payment ID

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))

    # Provider-specific raw data (entire webhook payload)
    provider_data = Column(JSON)

    # Payment method details
    payment_method = Column(String(50))  # e.g., 'credit_card', 'paypal_balance'
    payment_method_details = Column(JSON)  # Card last4, network, etc.

    # Refunds and fees
    fees = Column(Numeric(10, 2))
    tax = Column(Numeric(10, 2))
    refund_id = Column(String(255))  # For refund transactions

    # International payments
    country_code = Column(String(2))

    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_transaction_id", name="uq_provider_transaction"
        ),
    )
