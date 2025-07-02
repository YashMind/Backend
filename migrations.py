from sqlalchemy.orm import Session
import sqlalchemy.exc as sa_exc
from sqlalchemy import text  # For raw SQL if needed
from config import SessionLocal, Base
from models.adminModel.adminModel import SubscriptionPlans
from models.authModel.authModel import AuthUser
from models.subscriptions.userCredits import HistoryUserCredits, UserCredits


def ensure_tables_exist(db: Session):
    """Create tables if they don't exist"""
    Base.metadata.create_all(db.get_bind())


def upgrade_subscription_plans(db: Session):
    try:
        # Ensure base tables exist
        ensure_tables_exist(db)

        # Add new columns if they don't exist
        for column in ["chars_allowed", "webpages_allowed", "team_strength"]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE subscription_plans 
                        ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()  # Column already exists, ignore
                else:
                    raise

        # Now ORM query is safe
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


def update_user_credits(db: Session):
    # 1. First add the new columns if they don't exist
    try:
        ensure_tables_exist(db)
        # 1. Add columns if they don't exist
        for column in ["chars_allowed", "webpages_allowed", "team_strength"]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE user_credits 
                        ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()  # Column already exists, ignore
                else:
                    raise

        # 2. Update values based on plan type
        # Get all plans first (more efficient than querying for each credit)
        plans = db.query(SubscriptionPlans).all()
        plan_dict = {plan.id: plan for plan in plans}

        # Get all credits
        credits = db.query(UserCredits).all()

        for credit in credits:
            plan = plan_dict.get(credit.plan_id)
            if not plan:
                continue

            if plan.name in ["Basic", "Trial"]:
                credit.chars_allowed = 10000000
                credit.webpages_allowed = 2000
                credit.team_strength = 5
            elif plan.name == "Pro":
                credit.chars_allowed = 20000000
                credit.webpages_allowed = 10000
                credit.team_strength = 10
            elif plan.name == "Enterprise":
                credit.chars_allowed = 50000000
                credit.webpages_allowed = 30000
                credit.team_strength = 20

        db.commit()
        print("✅ Migration completed successfully")

    except sa_exc.SQLAlchemyError as e:
        db.rollback()
        print(f"❌ Database error during migration: {str(e)}")
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Unexpected error during migration: {str(e)}")
        raise


def update_history_user_credits(db: Session):
    # 1. First add the new columns if they don't exist
    try:
        ensure_tables_exist(db)
        # Method 1: Using SQLAlchemy DDL (recommended)
        for column in ["chars_allowed", "webpages_allowed", "team_strength"]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE history_user_credits 
                        ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()  # Column already exists, ignore
                else:
                    raise

        # Commit the schema changes first
        db.commit()
        # 2. Now update the values based on plan type
        plans = db.query(SubscriptionPlans).all()
        plan_dict = {plan.id: plan for plan in plans}
        credits = db.query(HistoryUserCredits).all()

        for credit in credits:
            plan = plan_dict.get(credit.plan_id)  # Get the associated plan
            if not plan:
                continue  # Skip if no plan found

            if plan.name in ["Basic", "Trial"]:
                credit.chars_allowed = 10000000
                credit.webpages_allowed = 2000
                credit.team_strength = 5
            elif plan.name == "Pro":
                credit.chars_allowed = 20000000
                credit.webpages_allowed = 10000
                credit.team_strength = 10
            elif plan.name == "Enterprise":
                credit.chars_allowed = 50000000
                credit.webpages_allowed = 30000
                credit.team_strength = 20

        db.commit()
        print("✅ Migration completed successfully")

    except sa_exc.SQLAlchemyError as e:
        db.rollback()
        print(f"❌ Database error during migration: {str(e)}")
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Unexpected error during migration: {str(e)}")
        raise


def main():
    db = SessionLocal()
    try:
        upgrade_subscription_plans(db)
        update_user_credits(db)
        update_history_user_credits(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
