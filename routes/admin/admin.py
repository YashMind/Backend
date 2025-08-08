from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    BackgroundTasks,
    Request,
    Response,
    Form,
    Query,
    Body,
)
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from models.activityLogModel.activityLogModel import ActivityLog
from utils.utils import decode_access_token, get_country_from_ip, get_current_user
from jose import JWTError, jwt
from uuid import uuid4
import json
from models.authModel.authModel import AuthUser
from models.adminModel.adminModel import (
    PaymentGateway,
    SubscriptionPlans,
    TokenBots,
    BotProducts,
)
from models.adminModel.roles_and_permission import RolePermission
from sqlalchemy.exc import SQLAlchemyError
from models.activityLogModel.activityLogModel import ActivityLog
from models.chatModel.sharing import ChatBotSharing
from models.chatModel.chatModel import ChatBots

from schemas.authSchema.authSchema import User, UserUpdate
from schemas.adminSchema.adminSchema import (
    PostEmail,
    PaymentGatewaySchema,
    PlansSchema,
    TokenBotsSchema,
    BotProductSchema,
    RolePermissionInput,
    RolePermissionResponse,
)
from sqlalchemy import func, or_, and_
from sqlalchemy.sql import exists

from sqlalchemy.orm import Session
from config import get_db, settings
from typing import Optional, Dict, List
from sqlalchemy import func, or_, desc, asc
import httpx
from datetime import datetime, timedelta
from config import SessionLocal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from decorators.rbac_admin import check_permissions
from decorators.public import public_route
from decorators.allow_roles import allow_roles

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.put("/users/{user_id}/base-rate")
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def update_base_rate(
    user_id: int, request: Request, data: User, db: Session = Depends(get_db)
):
    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.base_rate_per_token = data.base_rate_per_token
    db.commit()
    db.refresh(user)

    return {
        "success": True,
        "message": "Base rate updated successfully.",
        "data": {
            "id": user.id,
            "email": user.email,
            "base_rate_per_token": str(user.base_rate_per_token),
        },
    }

@router.get("/get-all-users")
@public_route()
async def get_all_users(
    
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search by name or email"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
    plan: Optional[str] = Query(
        None, description="Filter by plan: 1=Basic, 2=Pro, 3=Enterprise 4=Free 5=Team 6=cilent"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status: active, inactive, suspended"
    ),
    token_used: Optional[str] = Query(
        None, description="Filter by token range: 0-1000, 1001-5000, 5001+"
    ),
    message_used: Optional[str] = Query(
        None, description="Filter by token range: 0-100, 101-500, 501+"
    ),
    start_date: Optional[str] = Query(
        None, description="Start date for signup date range (YYYY-MM-DD)"
    ),
    end_date: Optional[str] = Query(
        None, description="End date for signup date range (YYYY-MM-DD)"
    ),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        now = datetime.utcnow()
        start_of_month = datetime(now.year, now.month, 1)

        # Calculate total signups this month
        total_signups = (
            db.query(AuthUser).filter(AuthUser.created_at >= start_of_month).count()
        )
        
        # Calculate total tokens consumed (all time)
        total_tokens_consumed = db.query(func.sum(AuthUser.tokenUsed)).scalar() or 0
        total_messages_consumed = db.query(func.sum(AuthUser.messageUsed)).scalar() or 0
        
        
        # Calculate total subscriptions (users with plan > 1 or active subscriptions)
        total_subscriptions = (
            db.query(AuthUser)
            .filter(AuthUser.plan > 1)  # Assuming plan 1 is free, 2+ are paid
            .count()
        )

        query = db.query(AuthUser)

        # Apply search
        if search:
            query = query.filter(
                or_(
                    AuthUser.fullName.ilike(f"%{search}%"),
                    AuthUser.email.ilike(f"%{search}%"),
                )
            )

        # Apply plan filter
        
        if plan:
            if plan.lower() == "all":  
                pass
            if plan =="4":
                query= query.filter(AuthUser.plan.is_(None))
                
            elif plan=="5":
                query = query.join(
                ChatBotSharing,
                ChatBotSharing.shared_user_id == AuthUser.id
                ).filter(
                ChatBotSharing.status == "active"
                )
            elif plan == "6":
                query = query.filter(
                ~exists().where(
                and_(
                ChatBotSharing.shared_user_id == AuthUser.id,
                ChatBotSharing.status == "active"
            )
            )
            )    
            else:
                query = query.filter(AuthUser.plan == int(plan))
            

        # Apply status filter
        if status:
            query = query.filter(AuthUser.status == status)

        # Apply token used filter
        if token_used:
            if token_used == "0-1000":
                query = query.filter(AuthUser.tokenUsed.between(0, 1000))
            elif token_used == "1001-5000":
                query = query.filter(AuthUser.tokenUsed.between(1001, 5000))
            elif token_used == "5001+":
                query = query.filter(AuthUser.tokenUsed >= 5001)

        if message_used:
            if token_used == "0-100":
                query = query.filter(AuthUser.messageUsed.between(0, 100))
            elif token_used == "101-500":
                query = query.filter(AuthUser.messageUsed.between(101, 500))
            elif token_used == "501+":
                query = query.filter(AuthUser.messageUsed >= 501)

        # Apply date range filter
        if start_date:
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(AuthUser.created_at >= start_date)
        if end_date:
            end_date = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(
                days=1
            )  # Include entire end day
            query = query.filter(AuthUser.created_at < end_date)

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
            "data": results,
            "total_signups": total_signups,
            "total_tokens_consumed": total_tokens_consumed,  # NEW: Total tokens consumed (all time)
            "total_subscriptions": total_subscriptions,  # NEW: Total subscriptions 
            "total_messages_consumed": total_messages_consumed
        }

    except HTTPException as http_exc:
        raise http_exc
    except ValueError as ve:
        print(ve)
        raise HTTPException(status_code=400, detail=f"Invalid filter value: {str(ve)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# update user
@router.put("/update-user-admin", response_model=User)
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def update_chatbot(
    data: User,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == int(data.id)).first()
        if not user: 
            raise HTTPException(status_code=404, detail="Chatbot not found")

        if data.status:
            user.status = data.status
        if data.tokenUsed == 0:
            user.tokenUsed = int(data.tokenUsed)

        if data.fullName:
            user.fullName = data.fullName

        if data.role:
            user.role = data.role

        if data.plan:
            user.plan = data.plan

        db.commit()
        db.refresh(user)
        log_entry = ActivityLog(
            user_id=current_user.id,
            username=current_user.fullName,
            role=current_user.role,
            action=f"{data.status}",
            log_activity=f"Account status updated to {data.status}",
        )
        db.add(log_entry)
        db.commit()
        return user

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/update-client-admin", response_model=User)
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def update_chatbot(data: User, request: Request, db: Session = Depends(get_db)):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == int(data.id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Chatbot not found")

        if data.status:
            user.status = data.status

        if data.tokenUsed == 0:
            user.tokenUsed = int(data.tokenUsed)

        if data.fullName:
            user.fullName = data.fullName

        if data.role:
            user.role = data.role

        if data.plan:
            user.plan = data.plan

        db.commit()
        db.refresh(user)
        return user

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# create new subscription plan
@router.post("/create-subscription-plans", response_model=PlansSchema)
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def create_subscription_plans(
    data: PlansSchema, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        id = data.id
        if id:
            existing_plan = (
                db.query(SubscriptionPlans)
                .filter(SubscriptionPlans.id == data.id)
                .first()
            )
            if not existing_plan:
                raise HTTPException(status_code=404, detail="Plan not found")

            existing_plan.name = data.name
            existing_plan.pricingInr = data.pricingInr
            existing_plan.pricingDollar = data.pricingDollar
            existing_plan.token_per_unit = data.token_per_unit
            existing_plan.chatbots_allowed = data.chatbots_allowed
            existing_plan.duration_days = data.duration_days
            existing_plan.features = data.features
            existing_plan.users_active = data.users_active
            existing_plan.chars_allowed = data.chars_allowed
            existing_plan.webpages_allowed = data.webpages_allowed
            existing_plan.team_strength = data.team_strength
            existing_plan.message_per_unit = data.message_per_unit

            db.commit()
            db.refresh(existing_plan)
            return existing_plan
        else:
            new_plan = SubscriptionPlans(
                name=data.name,
                pricingInr=data.pricingInr,
                pricingDollar=data.pricingDollar,
                token_per_unit=data.token_per_unit,
                chatbots_allowed=data.chatbots_allowed,
                duration_days=data.duration_days,
                features=data.features,
                users_active=data.users_active,
                chars_allowed=data.chars_allowed,
                webpages_allowed=data.webpages_allowed,
                team_strength=data.team_strength,
                message_per_unit=data.message_per_unit,
            )
            db.add(new_plan)
            db.commit()
            db.refresh(new_plan)

            # TODO: add activity log entry
            return new_plan
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
@router.post("/subscription-plans/{plan_id}/status")
async def update_plan_status(
    plan_id: int, is_active: bool = Body(..., embed=True), db: Session = Depends(get_db)
):
    plan = db.query(SubscriptionPlans).filter(SubscriptionPlans.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found.")

    plan.is_active = is_active
    db.commit()
    db.refresh(plan)

    return {
        "success": True,
        "message": f"Subscription plan {'activated' if is_active else 'deactivated'} successfully.",
        "data": {"id": plan.id, "is_active": plan.is_active},
    }


@router.get("/subscription-plans")
@check_permissions(["subscription-plans"])
async def get_all_subscription_plans_admin(
    request: Request, db: Session = Depends(get_db)
):
    try:
        plans = db.query(SubscriptionPlans).all()

        # Format plans with relevant fields
        formatted_plans = [
            {
                "id": plan.id,
                "name": plan.name,
                "pricingInr": plan.pricingInr,
                "pricingDollar": plan.pricingDollar,
                "token_per_unit": plan.token_per_unit,
                "chatbots_allowed": plan.chatbots_allowed,
                "chars_allowed": plan.chars_allowed,
                "webpages_allowed": plan.webpages_allowed,
                "team_strength": plan.team_strength,
                "duration_days": plan.duration_days,
                "features": plan.features,
                "users_active": plan.users_active,
                "is_active": plan.is_active,  # Include activation status
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
                "message_per_unit": plan.message_per_unit,
            }
            for plan in plans
        ]

        return {
            "success": True,
            "message": "Subscription plans fetched successfully.",
            "data": formatted_plans,
        }
    except SQLAlchemyError as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {str(db_err)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")


@router.get("/subscription-plans/public")
@public_route()
async def get_all_subscription_plans_public(
    request: Request, db: Session = Depends(get_db)
):
    try:
        plans = (
            db.query(SubscriptionPlans)
            .filter(
                SubscriptionPlans.is_active == True, SubscriptionPlans.is_trial == False
            )
            .all()
        )

        client_ip = request.client.host
        country = await get_country_from_ip(ip=client_ip)

        print("Country: ", country)

        formatted_plans = []
        # Format plans with relevant fields
        for plan in plans:
            pricing = plan.pricingDollar
            currency = "USD"
            if country == "IN":
                pricing = plan.pricingInr
                currency = "INR"
            formatted_plan = {
                "id": plan.id,
                "name": plan.name,
                "pricing": pricing,
                "currency": currency,
                "token_per_unit": plan.token_per_unit,
                "chatbots_allowed": plan.chatbots_allowed,
                "chars_allowed": plan.chars_allowed,
                "webpages_allowed": plan.webpages_allowed,
                "team_strength": plan.team_strength,
                "duration_days": plan.duration_days,
                "features": plan.features,
                "users_active": plan.users_active,
                "is_active": plan.is_active,  # ✅ Include activation status
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
                "message_per_unit": plan.message_per_unit,
            }
            formatted_plans.append(formatted_plan)

        return {
            "success": True,
            "message": "Subscription plans fetched successfully.",
            "data": formatted_plans,
        }
    except SQLAlchemyError as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {str(db_err)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")


@router.delete("/delete-subscription-plan/{plan_id}")
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def delete_subscription_plan(
    plan_id: int, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        plan = (
            db.query(SubscriptionPlans).filter(SubscriptionPlans.id == plan_id).first()
        )
        if plan:
            db.delete(plan)
            db.commit()
        return {"message": "Plan deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# create new subscription plan
@router.post("/create-token-bots", response_model=TokenBotsSchema)
async def create_subscription_plans(
    data: TokenBotsSchema, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        id = data.id
        if id:
            existing_plan = db.query(TokenBots).filter(TokenBots.id == data.id).first()
            if not existing_plan:
                raise HTTPException(status_code=404, detail="Plan not found")

            existing_plan.name = data.name
            existing_plan.pricing = data.pricing
            existing_plan.token_limits = data.token_limits
            existing_plan.message_limits = data.message_limits

            db.commit()
            db.refresh(existing_plan)
            return existing_plan
        else:
            new_botToken = TokenBots(
                name=data.name,
                pricing=data.pricing,
                token_limits=data.token_limits,
                message_limits=data.message_limits,
            )
            db.add(new_botToken)
            db.commit()
            db.refresh(new_botToken)
            return new_botToken

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-all-token-bots")
async def get_all_token_bots(
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(
        None, description="Search by document_link or target_link"
    ),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(TokenBots).filter()

        # Apply search
        if search:
            query = query.filter(
                or_(
                    TokenBots.name.ilike(f"%{search}%"),
                    TokenBots.features.ilike(f"%{search}%"),
                )
            )

        # Sorting
        sort_column = getattr(TokenBots, sort_by, TokenBots.created_at)
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
            "data": results,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-token-bot/{token_bot_id}")
async def delete_token_bots(
    token_bot_id: int, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        token_bot = db.query(TokenBots).filter(TokenBots.id == token_bot_id).first()
        if token_bot:
            db.delete(token_bot)
            db.commit()
        return {"message": "Token bot deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-top-consumption-users")
@check_permissions(["token-analytics"])
async def get_top_consumption_users(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # get top 10 most token consumption users
        top_users = (
            db.query(AuthUser)
            .filter(AuthUser.tokenUsed != None)
            .order_by(desc(AuthUser.tokenUsed))
            .limit(10)
            .all()
        )

        # Replace plan ID with full plan object for each user
        for user in top_users:
            user.plan = (
                db.query(SubscriptionPlans)
                .filter(SubscriptionPlans.id == user.plan)
                .first()
            )

        return top_users

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# update token bot
@router.put("/update-bot-token", response_model=TokenBotsSchema)
async def update_chatbot(data: TokenBotsSchema, db: Session = Depends(get_db)):
    try:
        token_bot = db.query(TokenBots).filter(TokenBots.id == int(data.id)).first()
        if not token_bot:
            raise HTTPException(status_code=404, detail="token bot not found")

        token_bot.active = data.active
        db.commit()
        db.refresh(token_bot)
        return token_bot

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# create update bot product
@router.post("/create-update-bot-product", response_model=BotProductSchema)
async def create_update_bot_product(
    data: BotProductSchema, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        id = data.id
        if id:
            existing_product = (
                db.query(BotProducts).filter(BotProducts.id == data.id).first()
            )
            if not existing_product:
                raise HTTPException(status_code=404, detail="Product not found")

            existing_product.active = data.active

            db.commit()
            db.refresh(existing_product)
            return existing_product
        else:
            new_bot_product = BotProducts(
                product_name=data.product_name, active=data.active
            )
            db.add(new_bot_product)
            db.commit()
            db.refresh(new_bot_product)
            return new_bot_product

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-bot-products")
async def get_bot_products(
    request: Request,
    db: Session = Depends(get_db),
    search: Optional[str] = Query(
        None, description="Search by document_link or target_link"
    ),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Number of items per page"),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        query = db.query(BotProducts).filter()

        # Apply search
        if search:
            query = query.filter(
                or_(
                    BotProducts.name.ilike(f"%{search}%"),
                    BotProducts.features.ilike(f"%{search}%"),
                )
            )

        # Sorting
        sort_column = getattr(BotProducts, sort_by, BotProducts.created_at)
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
            "data": results,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-admin-users", response_model=List[User])
async def get_top_consumption_users(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        # get top 10 most token consumption users
        admins = ["Super Admin", "Billing Admin", "Product Admin", "Support Admin"]
        admin_users = db.query(AuthUser).filter(AuthUser.role.in_(admins)).all()

        return admin_users
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-client-users", response_model=List[User])
async def get_non_admin_users(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Define admin roles
        admins = [
            "Admin",
            "Super Admin",
            "Billing Admin",
            "Product Admin",
            "Support Admin",
        ]

        # Query users with no role or role not in admin list
        non_admin_users = (
            db.query(AuthUser)
            .filter(~AuthUser.role.in_(admins) | (AuthUser.role == None))
            .all()
        )

        return non_admin_users
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-uninvited-users")
@public_route()
async def get_uninvited_users(
    request: Request, bot_id: int, db: Session = Depends(get_db)
):
    """
    Get all users who haven't been invited to the specified chatbot.
    This includes both regular users and admin users, but excludes the chatbot owner.
    """
    try:
        # Authenticate the user
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Get the current user to verify they have access to this chatbot
        current_user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if not current_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Get the chatbot to find the owner
        chatbot = db.query(ChatBots).filter(ChatBots.id == bot_id).first()
        if not chatbot:
            raise HTTPException(status_code=404, detail="Chatbot not found")

        # Verify the current user has access to this chatbot (either owner or invited user)
        has_access = False
        if chatbot.user_id == user_id:
            # User is the owner
            has_access = True
        else:
            # Check if user is invited to this chatbot
            sharing = (
                db.query(ChatBotSharing)
                .filter(
                    ChatBotSharing.bot_id == bot_id,
                    ChatBotSharing.shared_user_id == user_id,
                    ChatBotSharing.status == "active",
                )
                .first()
            )
            if sharing:
                has_access = True

        if not has_access:
            raise HTTPException(
                status_code=403, detail="You don't have access to this chatbot"
            )

        # Find all users who have already been invited to this chatbot
        invited_user_ids = (
            db.query(ChatBotSharing.shared_user_id)
            .filter(
                ChatBotSharing.bot_id == bot_id,
                ChatBotSharing.shared_user_id.isnot(None),
            )
            .all()
        )

        invited_emails = (
            db.query(ChatBotSharing.shared_email)
            .filter(
                ChatBotSharing.bot_id == bot_id, ChatBotSharing.shared_email.isnot(None)
            )
            .all()
        )

        # Extract the IDs and emails from the query results
        invited_user_ids = [
            user_id[0] for user_id in invited_user_ids if user_id[0] is not None
        ]
        invited_emails = [email[0] for email in invited_emails if email[0] is not None]

        # Get all users except:
        # 1. The current user making the request
        # 2. The chatbot owner
        # 3. Users who have already been invited
        uninvited_users = (
            db.query(AuthUser)
            .filter(
                AuthUser.id != user_id,  # Exclude the current user
                AuthUser.id != chatbot.user_id,  # Exclude the chatbot owner
                (
                    ~AuthUser.id.in_(invited_user_ids) if invited_user_ids else True
                ),  # Exclude already invited users by ID
                (
                    ~AuthUser.email.in_(invited_emails) if invited_emails else True
                ),  # Exclude already invited users by email
            )
            .all()
        )

        return uninvited_users

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-invited-users")
@public_route()
async def get_invited_users(
    request: Request,
    bot_id: int = None,
    page: int = 1,
    page_size: int = 10,
    search: str = None,
    status: str = None,
    db: Session = Depends(get_db),
):
    """
    Get paginated users who have been invited to chatbots owned by the current user.
    Supports pagination, search, and filtering.
    """
    try:
        # Authenticate the user
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Build the base query for sharing records
        query = (
            db.query(ChatBotSharing)
            .join(ChatBots)
            .filter(ChatBots.user_id == user_id)  # Only chatbots owned by current user
        )

        # Apply status filter
        if status and status != "all":
            query = query.filter(ChatBotSharing.status == status)
        else:
            # Default: exclude revoked unless specifically requested
            query = query.filter(ChatBotSharing.status.in_(["pending", "active"]))

        # If bot_id is provided, filter for that specific chatbot
        if bot_id:
            query = query.filter(ChatBotSharing.bot_id == bot_id)

        # Apply search filter if provided
        if search:
            search_term = f"%{search}%"
            # Join with AuthUser to search in user names
            query = query.outerjoin(
                AuthUser, ChatBotSharing.shared_user_id == AuthUser.id
            )
            query = query.filter(
                or_(
                    ChatBotSharing.shared_email.ilike(search_term),
                    AuthUser.fullName.ilike(search_term),
                    AuthUser.email.ilike(search_term),
                    ChatBots.chatbot_name.ilike(search_term),
                )
            )

        # Get total count before pagination
        total_count = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        sharing_records = query.offset(offset).limit(page_size).all()

        # Prepare the response with user and chatbot details
        invited_users = []
        for sharing in sharing_records:
            # Get chatbot details
            chatbot = db.query(ChatBots).filter(ChatBots.id == sharing.bot_id).first()

            user_info = {
                "sharing_id": sharing.id,
                "bot_id": sharing.bot_id,
                "chatbot_name": chatbot.chatbot_name if chatbot else "Unknown Chatbot",
                "status": sharing.status,
                "created_at": sharing.created_at,
                "updated_at": sharing.updated_at,
                "shared_email": sharing.shared_email,
                "user_name": None,
                "user_id": sharing.shared_user_id,
            }

            # If there's a shared_user_id, get the user details
            if sharing.shared_user_id:
                user = (
                    db.query(AuthUser)
                    .filter(AuthUser.id == sharing.shared_user_id)
                    .first()
                )
                if user:
                    user_info["user_name"] = user.fullName or "Unknown User"
                    user_info["shared_email"] = user.email

            invited_users.append(user_info)

        # Calculate pagination metadata
        total_pages = (total_count + page_size - 1) // page_size
        has_next = page < total_pages
        has_prev = page > 1

        return {
            "data": invited_users,
            "pagination": {
                "current_page": page,
                "page_size": page_size,
                "total_items": total_count,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
            },
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/revoke-access/{sharing_id}")
@public_route()
async def revoke_access(
    request: Request, sharing_id: int, db: Session = Depends(get_db)
):
    """
    Revoke access for a specific sharing record.
    Only the chatbot owner can revoke access.
    """
    try:
        # Authenticate the user
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Find the sharing record
        sharing = (
            db.query(ChatBotSharing).filter(ChatBotSharing.id == sharing_id).first()
        )

        if not sharing:
            raise HTTPException(status_code=404, detail="Sharing record not found")

        # Verify the user owns the chatbot
        chatbot = (
            db.query(ChatBots)
            .filter(ChatBots.id == sharing.bot_id, ChatBots.user_id == user_id)
            .first()
        )

        if not chatbot:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to revoke this access",
            )

        # Update the status to revoked
        sharing.status = "revoked"
        sharing.updated_at = datetime.now()

        db.commit()
        db.refresh(sharing)

        return {
            "success": True,
            "message": "Access revoked successfully",
            "sharing_id": sharing_id,
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/update-admin-user", response_model=UserUpdate)
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def update_admin_user(
    data: UserUpdate, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Missing access token")

        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        user_id = int(payload.get("user_id"))
        username = payload.get("username")
        role = payload.get("role")

        if not username or not role:
            raise HTTPException(status_code=401, detail="Incomplete token payload")

        if not data.id:
            raise HTTPException(status_code=404, detail="User ID is required")

        existing_user = db.query(AuthUser).filter(AuthUser.id == data.id).first()
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        if data.password:
            hashed_pw = pwd_context.hash(data.password)
            existing_user.password = hashed_pw

        existing_user.fullName = data.fullName
        existing_user.email = data.email
        existing_user.role = data.role
        existing_user.status = data.status
        # Skipping role_permissions update

        db.commit()
        db.refresh(existing_user)

        log_entry = ActivityLog(
            user_id=user_id,
            username=username,
            role=role,
            action="update",
            log_activity="Updated admin user details.",
        )
        db.add(log_entry)
        db.commit()

        return existing_user

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/update-client-user", response_model=UserUpdate)
async def update_client_user(
    data: UserUpdate, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        if not data.id:
            raise HTTPException(status_code=404, detail="user id is required")

        existing_user = db.query(AuthUser).filter(AuthUser.id == data.id).first()
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        if data.password:
            hashed_pw = pwd_context.hash(data.password)
            existing_user.password = hashed_pw

        existing_user.fullName = data.fullName
        existing_user.email = data.email

        # Only apply these fields if role is admin
        if data.role and data.role.lower().endswith("admin"):
            existing_user.role = data.role
            existing_user.status = data.status or "Active"
            existing_user.role_permissions = data.role_permissions
        else:
            # For client user, just keep role field
            existing_user.role = data.role

        db.commit()
        db.refresh(existing_user)
        return existing_user

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-admin-user/{id}")
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def delete_admin_user(
    id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        adminUser = db.query(AuthUser).filter(AuthUser.id == id).first()
        if adminUser:
            db.delete(adminUser)
            db.commit()

            log_entry = ActivityLog(
                user_id=current_user.id,
                username=current_user.fullName,
                role=current_user.role,
                action="delete",
                log_activity=f"Deleted user email {adminUser.email}",
            )
            db.add(log_entry)
            db.commit()

            return {"message": "Admin user deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Admin user not found")

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete-client-user/{id}")
@allow_roles(["Super Admin", "Billing Admin", "Product Admin", "Support Admin"])
async def delete_client_user(id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        clientUser = db.query(AuthUser).filter(AuthUser.id == id).first()
        if clientUser:
            db.delete(clientUser)
            db.commit()
        return {"message": "Plan deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get-admins-logs-activity")
async def get_admin_logs_activity(
    request: Request,
    db: Session = Depends(get_db),
    date_filter: Optional[str] = Query(
        None, description="Filter up to this date (YYYY-MM-DD)"
    ),
):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        admins = ["Super Admin", "Billing Admin", "Product Admin", "Support Admin"]

        # last_added_admin = db.query(AuthUser).filter(AuthUser.role.in_(admins)).order_by(desc(AuthUser.created_at)).first()

        # last_role_updated = db.query(AuthUser).filter(AuthUser.role.in_(admins)).order_by(desc(AuthUser.updated_at)).first()

        # last_suspended_admin = db.query(AuthUser).filter(AuthUser.role.in_(admins), AuthUser.status == "Suspend").order_by(desc(AuthUser.updated_at)).first()

        query = db.query(AuthUser).filter(AuthUser.role.in_(admins))

        if date_filter:
            try:
                parsed_date = datetime.strptime(date_filter, "%Y-%m-%d")
                query = query.filter(AuthUser.created_at <= parsed_date)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
                )

        last_added_admin = query.order_by(AuthUser.created_at.desc()).first()
        last_role_updated = query.order_by(AuthUser.updated_at.desc()).first()
        last_suspended_admin = (
            query.filter(AuthUser.status == "Suspend")
            .order_by(AuthUser.updated_at.desc())
            .first()
        )

        results = {
            "last_added_admin": last_added_admin,
            "last_role_updated": last_role_updated,
            "last_suspended_admin": last_suspended_admin,
        }

        return results
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# create update payment gateway
@router.post("/create-update-payment-gateway", response_model=PaymentGatewaySchema)
async def create_update_payment_gateway(
    data: PaymentGatewaySchema, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        id = data.id
        if id:
            existing_payment = (
                db.query(PaymentGateway).filter(PaymentGateway.id == data.id).first()
            )
            if not existing_payment:
                raise HTTPException(status_code=404, detail="Product not found")

            if data.payment_name:
                existing_payment.payment_name = data.payment_name
            if data.status:
                existing_payment.status = data.status
            if data.api_key:
                existing_payment.api_key = data.api_key

            db.commit()
            db.refresh(existing_payment)
            return existing_payment
        else:
            new_payment_gateway = PaymentGateway(
                payment_name=data.payment_name, status=data.status, api_key=data.api_key
            )
            db.add(new_payment_gateway)
            db.commit()
            db.refresh(new_payment_gateway)
            return new_payment_gateway

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# get payment gateway
@router.get("/get-payments-gateway", response_model=List[PaymentGatewaySchema])
async def get_payments_gateway(request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        payments_gateway = db.query(PaymentGateway).filter()
        return payments_gateway

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# delete payment gateway
@router.delete("/delete-payments-gateway/{id}")
async def delete_payments_gateway(
    id: int, request: Request, db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        payment_gateway = (
            db.query(PaymentGateway).filter(PaymentGateway.id == id).first()
        )
        if payment_gateway:
            db.delete(payment_gateway)
            db.commit()
        return {"message": "Payment gateway deleted successfully!"}

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assign", response_model=RolePermissionResponse)
def assign_custom_permissions(
    data: RolePermissionInput,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    print("User object:", current_user)
    print("User fields:", current_user.__dict__)

    # Check if role exists
    role_obj = db.query(RolePermission).filter_by(role=data.role).first()

    if role_obj:
        # Update permissions if role exists
        role_obj.permissions = data.permissions
    else:
        # Create new role with permissions
        role_obj = RolePermission(role=data.role, permissions=data.permissions)
        db.add(role_obj)

    db.commit()
    db.refresh(role_obj)
    log_entry = ActivityLog(
        user_id=current_user.id,
        username=current_user.fullName,
        role=current_user.role,
        action="role_updated",
        log_activity="Updated Permissions for role " + data.role,
    )
    db.add(log_entry)
    db.commit()
    return {"role": role_obj.role, "permissions": role_obj.permissions}


@router.get("/get", response_model=RolePermissionResponse)
def get_role_permissions(role: str, db: Session = Depends(get_db)):
    role_obj = db.query(RolePermission).filter_by(role=role).first()

    # Predefined system roles that should not throw 404 even if not in DB
    system_roles = {"Super Admin", "Billing Admin", "Product Admin", "Support Admin"}

    if not role_obj:
        if role in system_roles:
            return {
                "role": role,
                "permissions": [],  # Return empty by default if not found
            }
        else:
            raise HTTPException(status_code=404, detail="Role not found")

    return {"role": role_obj.role, "permissions": role_obj.permissions}


# Roles
@router.get("/roles_permissions")
@public_route()
async def fetch_roles(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    try:

        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")

        payload = decode_access_token(token)
        user_id = payload.get("user_id")
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=400, detail="User not found")

        role = user.role
        if not role:
            raise HTTPException(status_code=200, detail="User has no role")

        permissions = (
            db.query(RolePermission)
            .filter(func.lower(RolePermission.role) == func.lower(role))
            .first()
        )
        if not permissions:
            raise HTTPException(status_code=200, detail="User has no permissions")

        return {"permissions": permissions.permissions, "status": 200}

    except HTTPException as http_exc:
        error_response = JSONResponse(
            content={"detail": http_exc.detail}, status_code=http_exc.status_code
        )
        return error_response
