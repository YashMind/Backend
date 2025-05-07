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

    # MySQL connection string
    SQLALCHEMY_DATABASE_URL = (
        f"mysql+pymysql://{DB_USERNAME}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # JWT config
    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_ALGORITHM = os.getenv("DB_ALGORITHM", "HS512") # default from your config
    
    # Slack tokens
    SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
    SLACK_SIGNING_SECRET = os.getenv('SLACK_SIGNING_SECRET')
    SLACK_CLIENT_ID= os.getenv('SLACK_CLIENT_ID')
    SLACK_CLIENT_SECRET= os.getenv('SLACK_CLIENT_SECRET')

settings = Settings()

engine = create_engine(settings.SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


async def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
