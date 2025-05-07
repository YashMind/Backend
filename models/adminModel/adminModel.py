from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from config import Base

class SubscriptionPlans(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=True)
    pricing = Column(Integer, nullable=True)
    token_limits = Column(Integer, nullable=False)
    features = Column(String(255), nullable=True)
    users_active = Column(Integer, nullable=True)
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