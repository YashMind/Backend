from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

import os
from dotenv import load_dotenv

load_dotenv()  # loads from .env


class Settings:
    DB_USERNAME = os.getenv("DB_USERNAME")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    DB_HOST = os.getenv("DB_HOSTNAME")
    DB_PORT = os.getenv("DB_PORT", "3306")
    EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = os.getenv("SMTP_PORT")

    # SMTP2GO_USERNAME = os.getenv("SMTP2GO_USERNAME")
    # SMTP2GO_PASSWORD = os.getenv("SMTP2GO_PASSWORD")
    # EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")

    # MySQL connection string
    SQLALCHEMY_DATABASE_URL = (
        f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # JWT config
    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_ALGORITHM = os.getenv("DB_ALGORITHM", "HS512")  # default from your config

    # Slack tokens
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
    SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
    SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
    SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")

    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

    # Frontend URL for invitation links
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    CASHFREE_ENV = os.getenv("CASHFREE_ENV")
    CASHFREE_APP_ID = os.getenv("CASHFREE_APP_ID")
    CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY")
    CASHFREE_API_VERSION = os.getenv("CASHFREE_API_VERSION")

    PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
    PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
    PAYPAL_MODE = os.getenv("PAYPAL_MODE")
    PAYPAL_RETURN_URL = os.getenv("PAYPAL_RETURN_URL")
    PAYPAL_CANCEL_URL = os.getenv("PAYPAL_CANCEL_URL")
    PAYPAL_WEBHOOK_ID = os.getenv("PAYPAL_WEBHOOK_ID")

    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
    BASE_URL = os.getenv("BASE_URL")


settings = Settings()

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=280,
    pool_size=10,
    max_overflow=20,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db_sync():
    """Synchronous version of get_db for sync endpoints"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
