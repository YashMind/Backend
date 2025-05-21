from sqlalchemy.orm import Session
from config import SessionLocal
from models.adminModel.adminModel import SubscriptionPlans
from models.adminModel.productModel import Product 
from models.adminModel.toolsModal import ToolsUsed 
from models.adminModel.volumnDiscountModel import VolumeDiscount
from models.adminModel.roles_and_permission import RolePermission

def seed_subscription_plans(db: Session):
    default_plans = [
        {
            "name": "Basic",
            "pricing": 500,
            "token_limits": 1000,
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
            "token_limits": 1500,
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
            "token_limits": 2000,
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
            existing.pricing = plan["pricing"]
            existing.token_limits = plan["token_limits"]
            existing.features = plan["features"]
            existing.users_active = plan["users_active"]
        else:
            db.add(SubscriptionPlans(**plan))

def seed_products(db: Session):
    default_products = [
        {"name": "Chatbot", "status": "active"},
        {"name": "LLM", "status": "active"},
        {"name": "Voice Agent", "status": "active"},
    ]

    for product in default_products:
        existing = db.query(Product).filter_by(name=product["name"]).first()
        if existing:
            existing.status = product["status"]
        else:
            db.add(Product(**product))

def seed_tools(db: Session):
    # Define only the tools you want to keep
    default_tools = [
        {"name": "ChatGpt", "status": "active"},
        {"name": "Gemini", "status": "active"},
    ]

    # Keep track of tool names you want to preserve
    tool_names_to_keep = [tool["name"] for tool in default_tools]

    # Delete tools not in the current list
    db.query(ToolsUsed).filter(~ToolsUsed.name.in_(tool_names_to_keep)).delete(synchronize_session=False)

    # Upsert logic for current tools
    for tool in default_tools:
        existing = db.query(ToolsUsed).filter_by(name=tool["name"]).first()
        if existing:
            existing.status = tool["status"]
        else:
            db.add(ToolsUsed(**tool))

def seed_volume_discounts(db: Session):
    default_discounts = [
        {"min_tokens": 0,       "discount_percent": 0.0},
        {"min_tokens": 1_000_000, "discount_percent": 5.0},
        {"min_tokens": 5_000_000, "discount_percent": 10.0},
    ]

    for discount in default_discounts:
        existing = db.query(VolumeDiscount).filter_by(min_tokens=discount["min_tokens"]).first()
        if existing:
            existing.discount_percent = discount["discount_percent"]
        else:
            db.add(VolumeDiscount(**discount))

def seed_roles_and_permissions(db: Session):
    default_roles = [
        {
            "role": "Super Admin",
            "permissions": [
                "overview",
                "users-management",
                "subscription-plans",
                "token-analytics",
                "product-monitoring",
                "logs-activity",
                "enterprise-clients",
                "billing-settings",
                "users-roles",
                "support-communication"
            ]
        },
        {"role": "Billing Admin", "permissions": []},
        {"role": "Product Admin", "permissions": []},
        {"role": "Support Admin", "permissions": []},
    ]

    for role in default_roles:
        existing = db.query(RolePermission).filter_by(role=role["role"]).first()
        if existing:
            existing.permissions = role["permissions"]
        else:
            db.add(RolePermission(**role))


def main():
    db: Session = SessionLocal()
    seed_subscription_plans(db)
    seed_products(db)
    seed_tools(db)
    seed_volume_discounts(db)
    seed_roles_and_permissions(db)
    db.commit()
    db.close()
    print("✅ All seeds applied successfully.")


if __name__ == "__main__":
    main()
