from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from config import Base


class SubscriptionPlans(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=True)
    pricingInr = Column(Integer, nullable=True)
    pricingDollar = Column(Integer, nullable=True)
    token_per_unit = Column(Integer, nullable=False)
    chatbots_allowed = Column(Integer, nullable=False)
    chars_allowed = Column(Integer, nullable=False)
    webpages_allowed = Column(Integer, nullable=False)
    team_strength = Column(Integer, nullable=False)
    duration_days = Column(Integer, nullable=False)
    features = Column(String(255), nullable=True)
    users_active = Column(Integer, nullable=True)
    is_active = Column(Boolean, default=True)
    is_trial = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TokenBots(Base):
    __tablename__ = "token_bots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=True)
    pricing = Column(Integer, nullable=True)
    token_limits = Column(Integer, nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class BotProducts(Base):
    __tablename__ = "bot_products"

    id = Column(Integer, primary_key=True, index=True)
    product_name = Column(String(100), nullable=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PaymentGateway(Base):
    __tablename__ = "payment_gateway"

    id = Column(Integer, primary_key=True, index=True)
    payment_name = Column(String(255), nullable=True)
    status = Column(String(255), nullable=True)
    api_key = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
