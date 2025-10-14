from functools import wraps
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from inspect import signature
import inspect
from models.authModel.authModel import AuthUser
from utils.utils import decode_access_token

def public_route(return_user: bool = False):
    """
    Public route decorator that optionally authenticates and returns the user.
    
    Args:
        return_user: If True, will authenticate user and pass user object to route
    """
    def decorator(route_func):
        @wraps(route_func)
        async def wrapper(request: Request, *args, **kwargs):
            try:
                user = None
                
                # Get token from cookies or headers
                token = request.cookies.get("access_token") or request.headers.get("Authorization")
                db = kwargs.get('db')
                if not db or not isinstance(db, Session):
                    raise HTTPException(status_code=500, detail="Database session not available")
                
                if token:
                    # Here you would verify the token and get the user
                    # This is a placeholder for your authentication logic
                    try:
                        payload = decode_access_token(token)
                        user_id = payload.get("user_id")
                        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
                        if not user:
                            raise HTTPException(status_code=400, detail="User not found")
                    except Exception as auth_error:
                        if return_user:
                            raise HTTPException(
                                status_code=401,
                                detail="Invalid authentication credentials"
                            )
                
                # If user is required but not authenticated
                if return_user and not user:
                    raise HTTPException(
                        status_code=401,
                        detail="Authentication required"
                    )
                
                # Check if 'user' is a parameter of the wrapped function
                func_params = signature(route_func).parameters
                if "user" in func_params and return_user:
                    kwargs["user"] = user  # Pass 'user' only if it's needed
                
                # Proceed with the original function
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