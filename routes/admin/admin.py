from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response, Form, Query
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from utils.utils import create_access_token, decode_access_token, create_reset_token, send_reset_email, decode_reset_access_token, get_current_user
from jose import JWTError, jwt
from uuid import uuid4
import json
from models.authModel.authModel import AuthUser
from models.adminModel.adminModel import SubscriptionPlans
from schemas.authSchema.authSchema import User
from schemas.adminSchema.adminSchema import PlansSchema
from sqlalchemy.orm import Session
from config import get_db
from typing import Optional, Dict, List
from sqlalchemy import or_, desc, asc
import httpx
router = APIRouter()

@router.get("/get-all-users")
async def get_all_users(
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search by document_link or target_link"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(AuthUser).filter()

        # Apply search
        if search:
            query = query.filter(
                or_(
                    AuthUser.fullName.ilike(f"%{search}%"),
                    AuthUser.email.ilike(f"%{search}%"),
                )
            )

        # Sorting
        sort_column = getattr(AuthUser, sort_by, AuthUser.created_at)
        sort_column = desc(sort_column) if sort_order == "desc" else asc(sort_column)
        query = query.order_by(sort_column)

        # Pagination
        total_count = query.count()
        total_pages = (total_count + limit - 1) // limit
        results = query.offset((page - 1) * limit).limit(limit).all()


        return {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "data": results
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# update user
@router.put("/update-user-admin", response_model=User)
async def update_chatbot(data:User, db: Session = Depends(get_db)):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == int(data.id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Chatbot not found")

        if data.status:
            user.status = data.status
        if data.tokenUsed==0:
            user.tokenUsed = int(data.tokenUsed)
        db.commit()
        db.refresh(user)
        return user
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# create new chatbot
@router.post("/create-subscription-plans", response_model=PlansSchema)
async def create_subscription_plans(data:PlansSchema, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        id = data.id
        if id:
            existing_plan = db.query(SubscriptionPlans).filter(SubscriptionPlans.id == data.id).first()
            if not existing_plan:
                raise HTTPException(status_code=404, detail="Plan not found")

            existing_plan.name = data.name
            existing_plan.pricing = data.pricing
            existing_plan.token_limits = data.token_limits
            existing_plan.features = data.features
            existing_plan.users_active = data.users_active

            db.commit()
            db.refresh(existing_plan)
            return existing_plan
        else:
            new_plan = SubscriptionPlans(
                name=data.name,
                pricing=data.pricing,
                token_limits=data.token_limits,
                features=data.features,
                users_active=data.users_active
            )
            db.add(new_plan)
            db.commit()
            db.refresh(new_plan)
            return new_plan
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/get-all-subscription-plans")
async def get_all_subscription_plans(
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search by document_link or target_link"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(SubscriptionPlans).filter()

        # Apply search
        if search:
            query = query.filter(
                or_(
                    SubscriptionPlans.name.ilike(f"%{search}%"),
                    SubscriptionPlans.features.ilike(f"%{search}%"),
                )
            )

        # Sorting
        sort_column = getattr(SubscriptionPlans, sort_by, SubscriptionPlans.created_at)
        sort_column = desc(sort_column) if sort_order == "desc" else asc(sort_column)
        query = query.order_by(sort_column)

        # Pagination
        total_count = query.count()
        total_pages = (total_count + limit - 1) // limit
        results = query.offset((page - 1) * limit).limit(limit).all()


        return {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total_count,
            "data": results
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.delete("/delete-subscription-plan/{plan_id}")
async def delete_chat(plan_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        

        plan = db.query(SubscriptionPlans).filter(SubscriptionPlans.id==plan_id).first()
        if plan:
            db.delete(plan)
            db.commit()
        return {"message": "Plan deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
