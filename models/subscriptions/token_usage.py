from sqlalchemy import ForeignKey, Column, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config import Base


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("chat_bots.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    user_credit_id = Column(Integer)

    token_limit = Column(Integer)
    combined_token_consumption = Column(Integer)
    topup_transaction_id = Column(Integer, ForeignKey("transactions.id"))

    open_ai_request_token = Column(Integer, default=0)
    open_ai_response_token = Column(Integer, default=0)

    user_request_token = Column(Integer, default=0)
    user_response_token = Column(Integer, default=0)

    whatsapp_request_tokens = Column(Integer, default=0)
    whatsapp_response_tokens = Column(Integer, default=0)

    slack_request_tokens = Column(Integer, default=0)
    slack_response_tokens = Column(Integer, default=0)

    wordpress_request_tokens = Column(Integer, default=0)
    wordpress_response_tokens = Column(Integer, default=0)

    zapier_request_tokens = Column(Integer, default=0)
    zapier_response_tokens = Column(Integer, default=0)

    message_limit = Column(Integer)
    combined_message_consumption = Column(Integer)
    
    user_request_message = Column(Integer, default=0)
    user_response_message = Column(Integer, default=0)

    whatsapp_request_messages = Column(Integer, default=0)
    whatsapp_response_messages = Column(Integer, default=0)

    slack_request_messages = Column(Integer, default=0)
    slack_response_messages = Column(Integer, default=0)

    wordpress_request_messages = Column(Integer, default=0)
    wordpress_response_messages = Column(Integer, default=0)

    zapier_request_messages = Column(Integer, default=0)
    zapier_response_messages = Column(Integer, default=0)


class TokenUsageHistory(Base):
    __tablename__ = "history_token_usage"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("chat_bots.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    user_credit_id = Column(Integer)

    token_limit = Column(Integer)
    combined_token_consumption = Column(Integer)

    open_ai_request_token = Column(Integer, default=0)
    open_ai_response_token = Column(Integer, default=0)

    user_request_token = Column(Integer, default=0)
    user_response_token = Column(Integer, default=0)

    whatsapp_request_tokens = Column(Integer, default=0)
    whatsapp_response_tokens = Column(Integer, default=0)

    slack_request_tokens = Column(Integer, default=0)
    slack_response_tokens = Column(Integer, default=0)

    wordpress_request_tokens = Column(Integer, default=0)
    wordpress_response_tokens = Column(Integer, default=0)

    zapier_request_tokens = Column(Integer, default=0)
    zapier_response_tokens = Column(Integer, default=0)

    message_limit = Column(Integer)
    combined_message_consumption = Column(Integer)

    user_request_message = Column(Integer, default=0)
    user_response_message = Column(Integer, default=0)

    whatsapp_request_messages = Column(Integer, default=0)
    whatsapp_response_messages = Column(Integer, default=0)

    slack_request_messages = Column(Integer, default=0)
    slack_response_messages = Column(Integer, default=0)

    wordpress_request_messages = Column(Integer, default=0)
    wordpress_response_messages = Column(Integer, default=0)

    zapier_request_messages = Column(Integer, default=0)
    zapier_response_messages = Column(Integer, default=0)
