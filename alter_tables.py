from sqlalchemy import text
from sqlalchemy.orm import Session
from config import SessionLocal


def alter_tokens(db: Session):
    try:
        db.execute(text("""
            ALTER TABLE "ChatTotalToken"
            ADD COLUMN IF NOT EXISTS response_tokens INTEGER NOT NULL DEFAULT 0
        """))

        db.execute(text("""
            ALTER TABLE "ChatTotalToken"
            ADD COLUMN IF NOT EXISTS openai_tokens INTEGER NOT NULL DEFAULT 0
        """))
        
        db.execute(text("""
            ALTER TABLE "ChatTotalToken"
            RENAME COLUMN token_consumed TO user_message_tokens
        """))

        print("✅ Columns 'response_tokens' and 'openai_tokens' added to ChatTotalToken.")

    except Exception as e:
        db.rollback()
        print(f"❌ Error altering table: {e}")
        raise


def main():
    db: Session = SessionLocal()
    try:
        alter_tokens(db)
        db.commit()
        print("✅ All changes committed successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
