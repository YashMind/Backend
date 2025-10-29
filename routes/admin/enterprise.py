from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from config import get_db
from decorators.allow_roles import allow_roles
from models.adminModel.adminModel import SubscriptionPlans
from models.authModel.authModel import AuthUser

router = APIRouter(prefix="/enterprise", tags=["Enterprise Client"])

@router.get("/users")
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def get_enterprise_users(
    request:Request,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of records per page"),
    search: str = Query(None, description="Optional search by name or email"),
    db: Session = Depends(get_db),
):
    try:
        # Fetch all enterprise subscription plans
        enterprise_plans = (
            db.query(SubscriptionPlans)
            .filter(SubscriptionPlans.is_enterprise == True)
            .all()
        )

        if not enterprise_plans:
            return {"data": [], "total": 0, "message": "No enterprise plans found"}

        enterprise_plan_ids = [plan.id for plan in enterprise_plans]

        # Base query
        query = db.query(AuthUser, SubscriptionPlans.name.label("plan_name")).outerjoin(SubscriptionPlans, AuthUser.plan == SubscriptionPlans.id).filter(AuthUser.plan.in_(enterprise_plan_ids))

        # Optional search filter
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (AuthUser.fullName.ilike(search_pattern)) | (AuthUser.email.ilike(search_pattern))
            )

        # Total count before pagination
        total = query.count()

        # Pagination
        users = query.offset((page - 1) * limit).limit(limit).all()

        # Format response data
        formatted_results = []
        for user, plan_name in users:
            print("User",user.plan)
            user_data = {
                "id": user.id,
                "fullName": user.fullName,
                "email": user.email,
                "status": user.status,
                "created_at": user.created_at,
                "tokenUsed": user.tokenUsed,
                "messageUsed": user.messageUsed,
                "plan_id": user.plan,
                "plan": plan_name or "Free",  # Default if None
                "role":user.role,   
                "base_rate_per_message": user.base_rate_per_message
                    }
            formatted_results.append(user_data)
        
        return {
            "data": formatted_results,
            "total": total,
            "page": page,
            "limit": limit,
            "message": "Enterprise users fetched successfully",
        }

    except Exception as e:
        print(f"❌ Error fetching enterprise users: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
