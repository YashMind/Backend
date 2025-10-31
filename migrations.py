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


def update_chat_settings(db: Session):
    # 1. First add the new columns if they don't exist
    try:
        ensure_tables_exist(db)
        # Method 1: Using SQLAlchemy DDL (recommended)
        for column in ["popup_sound"]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE chat_settings 
                        ADD COLUMN {column} VARCHAR(255)
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
        print("✅ Migration completed successfully")

    except sa_exc.SQLAlchemyError as e:
        db.rollback()
        print(f"❌ Database error during migration: {str(e)}")
        raise
    except Exception as e:
        db.rollback()
        print(f"❌ Unexpected error during migration: {str(e)}")
        raise


def update_chat_bots(db: Session):
    # 1. First add the new columns if they don't exist
    try:
        ensure_tables_exist(db)
        # Method 1: Using SQLAlchemy DDL (recommended)
        for column in ["lead_email"]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE chat_bots 
                        ADD COLUMN {column} VARCHAR(255)
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()  # Column already exists, ignore
                else:
                    raise

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


def user_country_tracking(db: Session):
    try:
        ensure_tables_exist(db)
        for column in ["country"]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE users
                        ADD COLUMN {column} VARCHAR(255)
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()
                else:
                    raise

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


def add_message_per_unit_subscription(db: Session):
    try:
        ensure_tables_exist(db)
        for column in ["message_per_unit"]:
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
                    db.rollback()
                else:
                    raise

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


def users_messageUsed_tracking(db: Session):
    try:
        ensure_tables_exist(db)
        for column in ["messageUsed"]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE users
                        ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()
                else:
                    raise

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


def add_column_message_limit_combined_message_consumption_token_usage(db: Session):
    try:
        ensure_tables_exist(db)
        for column in ["message_limit", "combined_message_consumption"]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE token_usage
                        ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()
                else:
                    raise

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


def add_column_message_limit_combined_message_consumption_history_token_usage(
    db: Session,
):
    try:
        ensure_tables_exist(db)
        for column in [
            "message_limit",
            "combined_message_consumption",
            "user_request_message",
            "user_response_message",
            "whatsapp_request_messages",
            "whatsapp_response_messages",
            "slack_request_messages",
            "slack_response_messages",
            "wordpress_request_messages",
            "wordpress_response_messages",
            "zapier_request_messages",
            "zapier_response_messages",
        ]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE history_token_usage
                        ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()
                else:
                    raise

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


def add_column_message_per_unit_user_credits(db: Session):
    try:
        ensure_tables_exist(db)
        for column in [
            "message_per_unit",
            "credit_balance_messages",
            "credits_consumed_messages",
        ]:
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
                    db.rollback()
                else:
                    raise

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


def add_column_message_per_unit_history_user_credits(db: Session):
    try:
        ensure_tables_exist(db)
        for column in [
            "message_per_unit",
            "credit_balance_messages",
            "credits_consumed_messages",
        ]:
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
                    db.rollback()
                else:
                    raise

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

def add_columns_for_messages_tracking_token_usage(db: Session):
    try:
        ensure_tables_exist(db)
        for column in [
            "user_request_message",
            "user_response_message",
            "whatsapp_request_messages",
            "whatsapp_response_messages",
            "slack_request_messages",
            "slack_response_messages",
            "wordpress_request_messages",
            "wordpress_response_messages",
            "zapier_request_messages",
            "zapier_response_messages",
        ]:
            try:
                db.execute(
                    text(
                        f"""
                        ALTER TABLE token_usage
                        ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0
                    """
                    )
                )
                db.commit()
            except sa_exc.OperationalError as e:
                if "Duplicate column name" in str(e):
                    db.rollback()
                else:
                    raise

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

def create_settings_table(db: Session):
    try:
        print("📦 Creating table: settings ...")

        # Optional: Drop old table if it exists
        db.execute(text("DROP TABLE IF EXISTS failed_payment_notifications"))
        db.execute(text("DROP TABLE IF EXISTS settings"))

        # Create new `settings` table
        db.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS settings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                push_notification_admin_email VARCHAR(255) NOT NULL,
                toggle_push_notifications BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """
            )
        )

        db.commit()
        print("✅ Table created successfully!")

        # Verify table exists
        result = db.execute(
            text(
                """
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = DATABASE() 
            AND table_name = 'settings'
        """
            )
        ).scalar()

        if result > 0:
            print("✅ Table verified in database!")
        else:
            print("❌ Table created but not found in database!")

    except Exception as e:
        print(f"❌ Failed to create table: {str(e)}")
        db.rollback()
        raise
    # try:
    #     print("📦 Creating table: failed_payment_notifications ...")

    #     # Create the table using SQL
    #     db.execute(text("""
    #         CREATE TABLE IF NOT EXISTS failed_payment_notifications (
    #             id INT AUTO_INCREMENT PRIMARY KEY,
    #             payment_id VARCHAR(255) NOT NULL,
    #             user_id INT NOT NULL,
    #             user_email VARCHAR(255) NOT NULL,
    #             admin_email VARCHAR(255) NOT NULL,
    #             toggle_button BOOLEAN DEFAULT FALSE,
    #             email_sent BOOLEAN DEFAULT FALSE,
    #             email_sent_time DATETIME NULL,
    #             email_status ENUM('PENDING', 'SENT', 'FAILED') DEFAULT 'PENDING',
    #             amount DECIMAL(10, 2) NULL,
    #             currency VARCHAR(10) DEFAULT 'USD',
    #             payment_method VARCHAR(100) NULL,
    #             failure_reason TEXT NULL,
    #             error_code VARCHAR(100) NULL,
    #             raw_data TEXT NULL,
    #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    #             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    #             UNIQUE KEY unique_payment_id (payment_id)
    #         )
    #     """))

    #     db.commit()
    #     print("✅ Table created successfully!")

    #     # Verify table exists
    #     result = db.execute(text("""
    #         SELECT COUNT(*)
    #         FROM information_schema.tables
    #         WHERE table_schema = DATABASE()
    #         AND table_name = 'failed_payment_notifications'
    #     """)).scalar()

    #     if result > 0:
    #         print("✅ Table verified in database!")
    #     else:
    #         print("❌ Table created but not found in database!")

    # except Exception as e:
    #     print(f"❌ Failed to create table: {str(e)}")
    #     db.rollback()
    #     raise

def remove_foreign_key_from_user_credits(db):
    try:
        print(
            "📦 Removing foreign key constraints from plan_id in user_credits, history_user_credits, and transactions..."
        )

        tables = ["user_credits", "history_user_credits", "transactions"]

        for table in tables:
            fk_name_query = text(
                f"""
                SELECT CONSTRAINT_NAME 
                FROM information_schema.KEY_COLUMN_USAGE 
                WHERE TABLE_NAME = '{table}' 
                AND COLUMN_NAME = 'plan_id' 
                AND REFERENCED_TABLE_NAME = 'subscription_plans';
            """
            )
            fk_name = db.execute(fk_name_query).scalar()

            if fk_name:
                db.execute(text(f"ALTER TABLE {table} DROP FOREIGN KEY {fk_name};"))
                print(f"✅ Dropped foreign key '{fk_name}' from {table}.plan_id")
            else:
                print(f"ℹ️ No foreign key found on {table}.plan_id — skipping.")

        db.commit()
        print("✅ All foreign keys removed successfully!")

    except Exception as e:
        print(f"❌ Failed to remove foreign keys: {str(e)}")
        db.rollback()
        raise

def update_all_users_status_to_active(db):
    try:
        query = text('''
            UPDATE users
            SET status = 'Active'
            WHERE status IS NULL OR TRIM(status) = '';
        ''')
        db.execute(query)
        db.commit()
        print("✅ All users with empty or null status updated to Active.")
    except Exception as e:
        print(f"❌ Failed to update users: {str(e)}")
        db.rollback()
        raise

def update_all_users_role_to_user(db):
    try:
        query = text('''
            UPDATE users
            SET role = 'User'
            WHERE role IS NULL OR TRIM(status) = '';
        ''')
        db.execute(query)
        db.commit()
        print("✅ All users with empty or null role updated to User.")
    except Exception as e:
        print(f"❌ Failed to update users: {str(e)}")
        db.rollback()
        raise


def migrate_push_notification_email_field(db):
    try:
        # 1. Check if old column exists
        result = db.execute(text("SHOW COLUMNS FROM settings;")).fetchall()
        column_names = [col[0] for col in result]

        if "push_notification_admin_emails" not in column_names:
            print("🆕 Adding new JSON column 'push_notification_admin_emails'...")
            db.execute(text("ALTER TABLE settings ADD COLUMN push_notification_admin_emails JSON NULL;"))

        if "push_notification_admin_email" in column_names:
            print("📦 Migrating data from old column...")
            db.execute(text("""
                UPDATE settings
                SET push_notification_admin_emails = 
                    CASE 
                        WHEN push_notification_admin_email IS NOT NULL 
                             AND TRIM(push_notification_admin_email) <> ''
                        THEN JSON_ARRAY(push_notification_admin_email)
                        ELSE JSON_ARRAY()
                    END;
            """))

            print("🧹 Dropping old column 'push_notification_admin_email'...")
            db.execute(text("ALTER TABLE settings DROP COLUMN push_notification_admin_email;"))
        else:
            print("ℹ️ Old column not found; skipping data migration.")

        db.commit()
        print("✅ Migration completed successfully.")

    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {str(e)}")
        raise
    

def migrate_add_is_enterprise_field(db):
    """
    Adds a new boolean column 'is_enterprise' to the 'subscription_plans' table if it does not exist.
    """
    try:
        # 1. Check existing columns
        result = db.execute(text("SHOW COLUMNS FROM subscription_plans;")).fetchall()
        column_names = [col[0] for col in result]

        if "is_enterprise" not in column_names:
            print("🆕 Adding new column 'is_enterprise' to subscription_plans...")
            db.execute(text("ALTER TABLE subscription_plans ADD COLUMN is_enterprise BOOLEAN DEFAULT FALSE;"))
            db.commit()
            print("✅ Column 'is_enterprise' added successfully.")
        else:
            print("ℹ️ Column 'is_enterprise' already exists. No action taken.")

    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {str(e)}")
        raise

def migrate_rename_base_rate_column(db):
    """
    Renames column 'base_rate_per_token' to 'base_rate_per_message' in the 'users' table if it exists.
    """
    try:
        # 1. Check existing columns
        result = db.execute(text("SHOW COLUMNS FROM users;")).fetchall()
        column_names = [col[0] for col in result]

        # 2. Perform rename if applicable
        if "base_rate_per_token" in column_names and "base_rate_per_message" not in column_names:
            print("🆕 Renaming column 'base_rate_per_token' to 'base_rate_per_message' in 'users' table...")
            db.execute(text("ALTER TABLE users CHANGE base_rate_per_token base_rate_per_message FLOAT DEFAULT 0.0;"))
            db.commit()
            print("✅ Column renamed successfully.")
        elif "base_rate_per_message" in column_names:
            print("ℹ️ Column 'base_rate_per_message' already exists. No action taken.")
        else:
            print("⚠️ Column 'base_rate_per_token' not found in 'users' table. No action taken.")

    except Exception as e:
        db.rollback()
        print(f"❌ Migration failed: {str(e)}")


def main():
    db = SessionLocal()
    try:
        print("🚀 Starting migrations...")

        # create_settings_table(db)

        # Run all migrations
        # user_country_tracking(db)
        # upgrade_subscription_plans(db)
        # update_user_credits(db)
        # update_history_user_credits(db)
        # update_chat_settings(db)
        # update_chat_bots(db)
        # add_message_per_unit_subscription(db)
        # users_messageUsed_tracking(db)
        # add_column_message_limit_combined_message_consumption_token_usage(db)
        # add_column_message_limit_combined_message_consumption_history_token_usage(db)
        # add_column_message_per_unit_user_credits(db)
        # add_column_message_per_unit_history_user_credits(db)
        # add_columns_for_messages_tracking_token_usage(db)
        # remove_foreign_key_from_user_credits(db)
        # update_all_users_status_to_active(db)
        # update_all_users_role_to_user(db)
        # migrate_push_notification_email_field(db)
        # migrate_add_is_enterprise_field(db)
        # migrate_rename_base_rate_column(db)

        print("🎉 All migrations completed successfully!")

    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
