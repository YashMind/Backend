from sqlalchemy import (
    Boolean,
    ForeignKey,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Table,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config import Base
from models.subscriptions.transactionModel import Transaction


class UserCredits(Base):
    __tablename__ = "user_credits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    trans_id = Column(Integer, ForeignKey("transactions.id"))
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"))

    start_date = Column(DateTime, default=func.now())
    expiry_date = Column(DateTime)

    credits_purchased = Column(Integer)
    credits_consumed = Column(Integer, default=0)
    credit_balance = Column(Integer)

    token_per_unit = Column(Float)
    chatbots_allowed = Column(Integer)
    chars_allowed = Column(Integer)
    webpages_allowed = Column(Integer)
    team_strength = Column(Integer)

    is_trial = Column(Boolean, default=False)

    top_up_transactions = relationship(
        Transaction, secondary="user_credits_topups", backref="credited_users"
    )


user_credits_topups = Table(
    "user_credits_topups",
    Base.metadata,
    Column("user_credits_id", Integer, ForeignKey("user_credits.id")),
    Column("transaction_id", Integer, ForeignKey("transactions.id")),
)


class HistoryUserCredits(Base):
    __tablename__ = "history_user_credits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    trans_id = Column(Integer, ForeignKey("transactions.id"))
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"))

    start_date = Column(DateTime)
    expiry_date = Column(DateTime)

    credits_purchased = Column(Integer)
    credits_consumed = Column(Integer)
    credit_balance = Column(Integer)

    token_per_unit = Column(Float)
    chatbots_allowed = Column(Integer)
    chars_allowed = Column(Integer)
    webpages_allowed = Column(Integer)
    team_strength = Column(Integer)

    is_trial = Column(Boolean, default=False)

    expiry_reason = Column(String(255))
