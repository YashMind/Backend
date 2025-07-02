from sqlalchemy.orm import Session
from sqlalchemy import text  # For raw SQL if needed
from config import SessionLocal
from models.adminModel.adminModel import SubscriptionPlans, Base


def upgrade_subscription_plans(db: Session):
    # 1. First add the new columns if they don't exist
    try:
        # Method 1: Using SQLAlchemy DDL (recommended)
        db.execute(
            text(
                """
            ALTER TABLE subscription_plans 
            ADD COLUMN IF NOT EXISTS chars_allowed INTEGER NOT NULL DEFAULT 0
        """
            )
        )
        db.execute(
            text(
                """
            ALTER TABLE subscription_plans 
            ADD COLUMN IF NOT EXISTS webpages_allowed INTEGER NOT NULL DEFAULT 0
        """
            )
        )
        db.execute(
            text(
                """
            ALTER TABLE subscription_plans 
            ADD COLUMN IF NOT EXISTS team_strength INTEGER NOT NULL DEFAULT 0
        """
            )
        )

        # Commit the schema changes first
        db.commit()

        # 2. Now update the values based on plan type
        plans = db.query(SubscriptionPlans).all()

        for plan in plans:
            if plan.name in ["Basic", "Trial"]:
                plan.chars_allowed = 10000000
                plan.webpages_allowed = 2000
                plan.team_strength = 5
            elif plan.name == "Pro":
                plan.chars_allowed = 20000000
                plan.webpages_allowed = 10000
                plan.team_strength = 10
            elif plan.name == "Enterprise":
                plan.chars_allowed = 50000000
                plan.webpages_allowed = 30000
                plan.team_strength = 20

        db.commit()
        print("✅ Migration completed successfully")

    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {str(e)}")
        raise


def main():
    db = SessionLocal()
    try:
        upgrade_subscription_plans(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
