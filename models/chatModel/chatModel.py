import uuid
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    Text,
    Enum,
    TIMESTAMP,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from config import Base


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    bot_id = Column(Integer, nullable=False)
    title = Column(String(255), default="New Chat")
    created_at = Column(TIMESTAMP, server_default=func.now())
    token = Column(String(255), nullable=True)
    platform = Column(String(255), nullable=True)
    archived = Column(Boolean, default=False)
    messages = relationship("ChatMessage", back_populates="chat_session")


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chat_sessions.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    bot_id = Column(Integer, nullable=False)
    sender = Column(Enum("user", "bot", name="sender_enum"))
    message = Column(Text)
    created_at = Column(TIMESTAMP, server_default=func.now())
    chat_session = relationship("ChatSession", back_populates="messages")


class ChatBots(Base):
    __tablename__ = "chat_bots"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    chatbot_name = Column(String(255), nullable=False)
    train_from = Column(String(255), nullable=True)
    target_link = Column(String(255), nullable=True)
    document_link = Column(String(255), nullable=True)
    public = Column(Boolean, default=False)
    text_content = Column(Text, nullable=True)
    creativity = Column(Integer, default=0, nullable=True)
    token = Column(String(255), nullable=True)
    domains = Column(Text, nullable=True)
    lead_email = Column(String(255), nullable=True)
    limit_to = Column(Integer, nullable=True)
    every_minutes = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())

    def as_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "chatbot_name": self.chatbot_name,
            "train_from": self.train_from,
            "target_link": self.target_link,
            "document_link": self.document_link,
            "public": self.public,
            "text_content": self.text_content,
            "creativity": self.creativity,
            "token": self.token,
            "domains": self.domains,
            "lead_email": self.lead_email,
            "limit_to": self.limit_to,
            "every_minutes": self.every_minutes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ChatTotalToken(Base):
    __tablename__ = "chat_total_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    bot_id = Column(Integer, nullable=False)
    total_token = Column(Integer, nullable=False)
    user_message_tokens = Column(Integer, nullable=False)
    response_tokens = Column(Integer, nullable=False)
    openai_tokens = Column(Integer, nullable=False)
    plan = Column(Enum("basic", "pro", "ent", name="plan_enum"), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())


class ChatBotsFaqs(Base):
    __tablename__ = "chat_bots_faqs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    bot_id = Column(Integer, nullable=False)
    question = Column(String(255), nullable=True)
    answer = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())


class ChatBotsDocLinks(Base):
    __tablename__ = "chat_bots_doc_links"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    bot_id = Column(Integer, nullable=False)
    parent_link_id = Column(
        Integer, ForeignKey("chat_bots_doc_links.id"), nullable=True
    )  # Will save the parent link under which each link is created in recursive url loader of Full website training
    # for other types of training parent link be null
    # for full website parent link it will be same as the link id
    chatbot_name = Column(String(255), nullable=False)
    train_from = Column(String(255), nullable=True)
    target_link = Column(String(255), nullable=True)
    document_link = Column(String(255), nullable=True)
    public = Column(Boolean, default=False)
    text_content = Column(Text, nullable=True)
    status = Column(String(255), nullable=False)
    chars = Column(Integer, nullable=True)
    content_hash = Column(String(64), index=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())


class ChatBotsDocChunks(Base):
    __tablename__ = "chatbot_doc_chunks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    bot_id = Column(Integer)
    source = Column(String(255))
    content = Column(Text)  # chunked text
    chunk_index = Column(
        String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False
    )
    metaData = Column(Text)  # JSON string, optionally
    content_hash = Column(String(64))
    char_count = Column(Integer)
    link_id = Column(Integer, ForeignKey("chat_bots_doc_links.id"))
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())


class ChatBotLeadsModel(Base):
    __tablename__ = "chatbot_leads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    bot_id = Column(Integer)
    chat_id = Column(Integer)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True)
    contact = Column(String(255), nullable=True)
    message = Column(Text, nullable=True)
    type = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, onupdate=func.now())
