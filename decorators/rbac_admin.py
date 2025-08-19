from functools import wraps
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from utils.utils import decode_access_token
from models.authModel.authModel import AuthUser
from collections import defaultdict
from sqlalchemy.orm import Session
from models.subscriptions.transactionModel import Transaction   # Make sure this is your correct import path
from models.adminModel.roles_and_permission import RolePermission
import inspect

accessPoints = [
    'overview',
    'users-management',
    'subscription-plans',
    'token-analytics',
    'product-monitoring',
    'logs-activity',
    'enterprise-clients',
    'billing-settings',
    'users-roles',
    'support-communication',
]

# def check_permissions(required_permissions: list[str]):
#     def decorator(route_func):
#         @wraps(route_func)
#         async def wrapper(request: Request, *args, **kwargs):
#             try:
#                 # Get database session from kwargs
#                 db = kwargs.get('db')
#                 if not db or not isinstance(db, Session):
#                     raise HTTPException(status_code=500, detail="Database session not available")

#                 # Get token from cookies
#                 token = request.cookies.get("access_token")
#                 if not token:
#                     raise HTTPException(status_code=401, detail="Not authenticated")

#                 # Decode token and get user
#                 payload = decode_access_token(token)
#                 user_id = payload.get("user_id")
#                 user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
#                 if not user:
#                     raise HTTPException(status_code=400, detail="User not found")

#                 # Get user's role
#                 role = user.role
#                 if not role:
#                     raise HTTPException(status_code=403, detail="User has no role")

#                 # Get permissions for the role
#                 role_permissions = db.query(RolePermission).filter(
#                     func.lower(RolePermission.role) == role.lower()
#                 ).first()

#                 if not role_permissions:
#                     raise HTTPException(status_code=403, detail="No permissions found for this role")

#                 # Check if user has all required permissions
#                 user_permissions = role_permissions.permissions or []
#                 missing_permissions = [
#                     perm for perm in required_permissions 
#                     if perm not in user_permissions
#                 ]

#                 if missing_permissions:
#                     raise HTTPException(
#                         status_code=403,
#                         detail=f"Missing permissions: {', '.join(missing_permissions)}"
#                     )

#                 # All checks passed, proceed with the original function
#                 result = route_func(request, *args, **kwargs)
#                 if inspect.iscoroutine(result):
#                     return await result
#                 return result
            
#             except HTTPException as http_exc:
#                 return JSONResponse(
#                     content={"detail": http_exc.detail},
#                     status_code=http_exc.status_code
#                 )

#         return wrapper
#     return decorator

def check_permissions(required_permissions: list[str], allow_anonymous=False):
    def decorator(route_func):
        @wraps(route_func)
        async def wrapper(request: Request, *args, **kwargs):
            try:
                db = kwargs.get('db')
                if not db or not isinstance(db, Session):
                    raise HTTPException(status_code=500, detail="Database session not available")

                token = request.cookies.get("access_token")

                # No token → allow if anonymous
                if not token:
                    if allow_anonymous:
                        result = route_func(request, *args, **kwargs)
                        if inspect.iscoroutine(result):
                            return await result
                        return result
                    else:
                        raise HTTPException(status_code=401, detail="Not authenticated")

                # Decode token
                payload = decode_access_token(token)
                user_id = payload.get("user_id")
                print(user_id)
                user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
                if not user:
                    raise HTTPException(status_code=400, detail="User not found")

                role = user.role

                # If role missing
                if not role:
                    if allow_anonymous:
                        result = route_func(request, *args, **kwargs)
                        if inspect.iscoroutine(result):
                            return await result
                        return result
                    else:
                        raise HTTPException(status_code=403, detail="User has no role")

                # Get role permissions
                role_permissions = db.query(RolePermission).filter(
                    func.lower(RolePermission.role) == role.lower()
                ).first()

                # If role_permissions missing
                if not role_permissions:
                    if allow_anonymous:
                        result = route_func(request, *args, **kwargs)
                        if inspect.iscoroutine(result):
                            return await result
                        return result
                    else:
                        raise HTTPException(status_code=403, detail="No permissions found for this role")

                user_permissions = role_permissions.permissions or []

                # Check for missing permissions
                missing_permissions = [
                    perm for perm in required_permissions 
                    if perm not in user_permissions
                ]

                if missing_permissions:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Missing permissions: {', '.join(missing_permissions)}"
                    )

                # Run the route function
                result = route_func(request, *args, **kwargs)
                if inspect.iscoroutine(result):
                    return await result
                return result

            except HTTPException as http_exc:
                return JSONResponse(
                    content={"detail": http_exc.detail},
                    status_code=http_exc.status_code
                )

        return wrapper
    return decorator



def get_grouped_transaction_stats(db: Session, group_by: str = "monthly"):
    format_map = {
        "daily": "%Y-%m-%d",
        "monthly": "%Y-%m",
        "yearly": "%Y",
    }

    if group_by not in format_map:
        raise ValueError("Invalid group_by value. Must be one of: daily, monthly, yearly")

    time_format = format_map[group_by]

    # Success Transactions
    success_statuses = ['success', 'completed', 'paid', 'confirmed']
    success_query = (
        db.query(
            func.date_format(Transaction.created_at, time_format).label("period"),
            Transaction.currency,
            func.count().label("count"),
            func.sum(Transaction.amount).label("total_amount")
        )
        .filter(Transaction.status.in_(success_statuses))
        .group_by("period", Transaction.currency)
        .order_by("period")
        .all()
    )

    # Pending Transactions
    pending_query = (
        db.query(
            func.date_format(Transaction.created_at, time_format).label("period"),
            Transaction.currency,
            func.count().label("count"),
            func.sum(Transaction.amount).label("total_amount")
        )
        .filter(Transaction.status == 'pending')  # Adjust if you have other pending statuses
        .group_by("period", Transaction.currency)
        .order_by("period")
        .all()
    )

    def format_result(result):
        stats = defaultdict(list)
        for period, currency, count, total_amount in result:
            stats[currency.upper()].append({
                "period": period,
                "count": count,
                "total_amount": float(total_amount)
            })
        return stats

    return {
        "success": format_result(success_query),
        "pending": format_result(pending_query),
    }        
        