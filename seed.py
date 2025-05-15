from sqlalchemy.orm import Session
from config import SessionLocal 
from models.adminModel.adminModel import SubscriptionPlans

def seed_subscription_plans():
    db: Session = SessionLocal()

    default_plans = [
        {
            "name": "Basic",
            "pricing": 500,
            "token_limits": 1000,  # Rs. 1 per 1000 tokens
            "features": (
                "2 Chatbots, Rs. 1 per 1000 tokens, "
                "10 Million Characters, Crawl 2000 Website Pages, "
                "5 Team Members"
            ),
            "users_active": 500
        },
        {
            "name": "Pro",
            "pricing": 3000,
            "token_limits": 1500,  # Rs. 1 per 1500 tokens
            "features": (
                "10 Chatbots, Rs. 1 per 1500 tokens, "
                "20 Million Characters, Crawl 10,000 Website Pages, "
                "10 Team Members"
            ),
            "users_active": 350
        },
        {
            "name": "Enterprise",
            "pricing": 10000,
            "token_limits": 2000,  # Rs. 1 per 2000 tokens
            "features": (
                "30 Chatbots, Rs. 1 per 2000 tokens, "
                "50 Million Characters, Crawl 30,000 Website Pages, "
                "30 Team Members"
            ),
            "users_active": 200
        },
    ]
    for plan in default_plans:
        existing = db.query(SubscriptionPlans).filter_by(name=plan["name"]).first()
        if existing:
            # Update existing values
            existing.pricing = plan["pricing"]
            existing.token_limits = plan["token_limits"]
            existing.features = plan["features"]
            existing.users_active = plan["users_active"]
        else:
            new_plan = SubscriptionPlans(**plan)
            db.add(new_plan)

    db.commit()
    db.close()
    print("✅ Subscription plans seeded successfully.")

if __name__ == "__main__":
    seed_subscription_plans()
