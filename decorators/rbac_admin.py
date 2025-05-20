from functools import wraps
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from utils.utils import decode_access_token
from models.authModel.authModel import AuthUser
from models.adminModel.roles_and_permission import RolePermission

accessPoints = [
    'overview',
    'user-management',
    'subscription-plans',
    'token-analytics',
    'product-monitoring',
    'logs-activity',
    'enterprise-clients',
    'billing-settings',
    'users-roles',
    'support-communication',
]

def check_permissions(required_permissions: list[str]):
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            try:
                # Get database session from kwargs
                db = kwargs.get('db')
                if not db or not isinstance(db, Session):
                    raise HTTPException(status_code=500, detail="Database session not available")
                
                # Get token from cookies
                token = request.cookies.get("access_token")
                if not token:
                    raise HTTPException(status_code=401, detail="Not authenticated")

                # Decode token and get user
                payload = decode_access_token(token)
                user_id = payload.get("user_id")
                user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
                if not user:
                    raise HTTPException(status_code=400, detail="User not found")
                
                # Get user's role
                role = user.role
                if not role:
                    raise HTTPException(status_code=403, detail="User has no role")
                
                # Get permissions for the role
                role_permissions = db.query(RolePermission).filter(
                    func.lower(RolePermission.role) == func.lower(role)
                ).first()
                
                if not role_permissions:
                    raise HTTPException(status_code=403, detail="No permissions found for this role")
                
                # Check if user has all required permissions
                user_permissions = role_permissions.permissions
                missing_permissions = [
                    perm for perm in required_permissions 
                    if perm not in user_permissions
                ]
                
                if missing_permissions:
                    raise HTTPException(
                        status_code=403,
                        detail=f"Missing permissions: {', '.join(missing_permissions)}"
                    )
                
                # All checks passed, proceed with the original function
                return await func(request, *args, **kwargs)
            
            except HTTPException as http_exc:
                return JSONResponse(
                    content={"detail": http_exc.detail},
                    status_code=http_exc.status_code
                )
        
        return wrapper
    return decorator