from functools import wraps
from sqlalchemy import func
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from models.adminModel.productModel import Product
from sqlalchemy.orm import Session


def check_product_status(product: str):
    def decorator(route_func):
        @wraps(route_func)
        async def wrapper(*args, **kwargs):
            try:
                # Get database session from kwargs
                db = kwargs.get('db')
                if not db or not isinstance(db, Session):
                    raise HTTPException(status_code=500, detail="Database session not available")
                
                # Get token from cookies
                is_active = db.query(Product).filter(func.lower(Product.name) == func.lower(product)).first()
                if is_active.status == "deactive":
                    raise HTTPException(
                        status_code=403,
                        detail=f"Product is not active"
                    )
                
                # All checks passed, proceed with the original function
                return await route_func(*args, **kwargs)
                
            except HTTPException as http_exc:
                return JSONResponse(
                    content={"detail": http_exc.detail},
                    status_code=http_exc.status_code
                )
        
        return wrapper
    return decorator