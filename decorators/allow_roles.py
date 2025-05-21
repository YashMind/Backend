from functools import wraps
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from inspect import signature

from models.authModel.authModel import AuthUser
from models.adminModel.roles_and_permission import RolePermission
from utils.utils import decode_access_token


def allow_roles(allowed_roles: list[str]):
    allowed_roles_normalized = [r.strip().lower() for r in allowed_roles]

    def decorator(route_func):
        @wraps(route_func)
        async def wrapper(*args, **kwargs):
            print("Decorator triggered: Checking roles")

            request = None
            db = None

            # Extract Request and DB session
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    print(f"Found Request in args: {request}")
                elif isinstance(arg, Session):
                    db = arg
                    print(f"Found DB Session in args: {db}")

            if not request:
                request = kwargs.get("request")
                print(f"Request from kwargs: {request}")
            if not db:
                db = kwargs.get("db")
                print(f"DB session from kwargs: {db}")

            if not request:
                print("Request parameter missing")
                return JSONResponse(status_code=500, content={"detail": "Request parameter missing"})
            if not db:
                print("Database session parameter missing")
                return JSONResponse(status_code=500, content={"detail": "Database session parameter missing"})

            token = request.cookies.get("access_token") or request.headers.get("Authorization")
            print(f"Token found: {token}")
            if not token:
                print("Authentication required: No token")
                return JSONResponse(status_code=401, content={"detail": "Authentication required"})

            try:
                payload = decode_access_token(token)
                print(f"Decoded token payload: {payload}")

                user_id = payload.get("user_id")
                print(f"User ID from token: {user_id}")
                if not user_id:
                    raise HTTPException(status_code=401, detail="Invalid token payload")

                user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
                if not user:
                    raise HTTPException(status_code=404, detail="User not found")

                print(f"User ID: {user.id}, Email: {user.email}, Role: {user.role}")

                role_record = db.query(RolePermission).filter(RolePermission.role == user.role).first()
                print(f"Role record from DB: {role_record}")

                if not role_record:
                    print("No role record found for user's role")
                    raise HTTPException(status_code=403, detail="Access denied: No role found")

                role_name_normalized = role_record.role.strip().lower()
                print(f"Normalized role name: {role_name_normalized}")
                print(f"Allowed roles: {allowed_roles_normalized}")

                if role_name_normalized not in allowed_roles_normalized:
                    raise HTTPException(status_code=403, detail="Access denied: Unauthorized role")

            except HTTPException as e:
                print(f"HTTPException caught: {e.detail}")
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
            except Exception as e:
                print(f"Exception caught: {str(e)}")
                return JSONResponse(status_code=401, content={"detail": "Invalid authentication credentials"})

            if "user" in signature(route_func).parameters:
                kwargs["user"] = user
                print("Injected user into route function kwargs")

            print("Access granted, calling route function")
            return await route_func(*args, **kwargs)

        return wrapper
    return decorator
