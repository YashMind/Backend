from sqlalchemy import ForeignKey, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config import Base

class UserCredits(Base):
    __tablename__ = "user_credits"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    trans_id = Column(Integer, ForeignKey('transactions.id'))
    plan_id = Column(Integer, ForeignKey('subscription_plans.id'))
    
    start_date = Column(DateTime, default=func.now())
    expiry_date = Column(DateTime)
    
    credits_purchased = Column(Integer)
    credits_consumed = Column(Integer, default=0)
    credit_balance = Column(Integer)
    
    token_per_unit = Column(Float)
    chatbots_allowed = Column(Integer)
    
    # Relationships
    user = relationship("User", back_populates="credits")
    transaction = relationship("Transaction", back_populates="credits")
    plan = relationship("SubscriptionPlan", back_populates="credits")
    token_usages = relationship("TokenUsage", back_populates="user_credit")

class HistoryUserCredits(Base):
    __tablename__ = "history_user_credits"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    trans_id = Column(Integer, ForeignKey('transactions.id'))
    plan_id = Column(Integer, ForeignKey('subscription_plans.id'))
    
    start_date = Column(DateTime)
    expiry_date = Column(DateTime)
    
    credits_purchased = Column(Integer)
    credits_consumed = Column(Integer)
    credit_balance = Column(Integer)
    
    token_per_unit = Column(Float)
    chatbots_allowed = Column(Integer)
    
    expiry_reason = Column(String(255))
    
    # Relationships
    user = relationship("User", back_populates="history_credits")
    transaction = relationship("Transaction", back_populates="history_credits")
    plan = relationship("SubscriptionPlan", back_populates="history_credits")




