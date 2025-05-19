from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, Response, Form, Query,Body
from fastapi.responses import JSONResponse
from passlib.context import CryptContext
from utils.utils import decode_access_token, get_current_user
from jose import JWTError, jwt
from uuid import uuid4
import json
from models.authModel.authModel import AuthUser
from models.adminModel.adminModel import SubscriptionPlans, TokenBots, BotProducts
from models.adminModel.roles_and_permission import RolePermission
from sqlalchemy.exc import SQLAlchemyError

from schemas.authSchema.authSchema import User, UserUpdate
from schemas.adminSchema.adminSchema import PostEmail, PaymentGatewaySchema, PlansSchema, TokenBotsSchema, BotProductSchema,RolePermissionInput, RolePermissionResponse
from sqlalchemy.orm import Session
from config import get_db,settings
from typing import Optional, Dict, List
from sqlalchemy import or_, desc, asc
import httpx
from datetime import datetime
router = APIRouter()
from config import SessionLocal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

# def send_emails_in_batches(subject: str, content: str):
#     db: Session = SessionLocal()
#     users = db.query(AuthUser).with_entities(AuthUser.email).all()
#     recipient_emails = [u.email for u in users if u.email]

#     for email in recipient_emails:
#         try:
#             msg = MIMEMultipart()
#             msg["From"] = settings.EMAIL_ADDRESS
#             msg["To"] = email
#             msg["Subject"] = subject
#             msg.attach(MIMEText(content, "html"))

#             with smtplib.SMTP("mail.smtp2go.com", 587) as server:
#                 server.starttls()
#                 server.login(settings.SMTP2GO_USERNAME, settings.SMTP2GO_PASSWORD)
#                 server.send_message(msg)

#             print(f"Email sent to {email}")
#         except Exception as e:
#             print(f"Failed to send email to {email}: {e}")

router = APIRouter()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
from models.activityLogModel.activityLogModel import ActivityLog
from send_email import send_email

def send_emails_in_batches(subject: str, content: str, recipients: List[str]):
    batch_size = 50  # adjust based on your SMTP or provider limits
    for i in range(0, len(recipients), batch_size):
        batch = recipients[i:i + batch_size]
        send_email(subject=subject, html_content=content, recipients=batch)

@router.post("/send-emails")
def send_post_to_users(payload: PostEmail, background_tasks: BackgroundTasks):
    try:
        if not payload.recipients or len(payload.recipients) == 0:
            raise HTTPException(status_code=400, detail="At least one recipient is required.")
        
        content = f"<h3>{payload.title}</h3><p>{payload.description}</p>"
        background_tasks.add_task(send_emails_in_batches, payload.title, content, payload.recipients)
        return {"message": "Emails are being sent in the background"}
    
    except HTTPException as e:
        # re-raise specific validation errors
        raise e

    except Exception as e:
        print(f"Error occurred while queuing email task: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while sending emails.")


@router.put("/users/{user_id}/base-rate")
async def update_base_rate(user_id: int, data: User, db: Session = Depends(get_db)):
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
            "base_rate_per_token": str(user.base_rate_per_token)
        }
    }


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

        now = datetime.utcnow()
        start_of_month = datetime(now.year, now.month, 1)

        total_signups = db.query(AuthUser).filter(AuthUser.created_at >= start_of_month).count()
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
            "data": results,
            "total_signups": total_signups
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# update user
@router.put("/update-user-admin", response_model=User)
async def update_chatbot(data:User, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == int(data.id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Chatbot not found")

        if data.status:
            user.status = data.status
        if data.tokenUsed==0:
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
async def update_chatbot(data:User, db: Session = Depends(get_db)):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == int(data.id)).first()
        if not user:
            raise HTTPException(status_code=404, detail="Chatbot not found")

        if data.status:
            user.status = data.status

        if data.tokenUsed==0:
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

@router.post("/subscription-plans/{plan_id}/status")
async def update_plan_status(
    plan_id: int,
    is_active: bool = Body(..., embed=True),
    db: Session = Depends(get_db)
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
        "data": {"id": plan.id, "is_active": plan.is_active}
    }        
    
@router.get("/subscription-plans")
async def get_all_subscription_plans(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        plans = db.query(SubscriptionPlans).all()

        # Format plans with relevant fields
        formatted_plans = [
            {
                "id": plan.id,
                "name": plan.name,
                "pricing": plan.pricing,
                "token_limits": plan.token_limits,
                "features": plan.features,
                "users_active": plan.users_active,
                "is_active": plan.is_active,  # ✅ Include activation status
                "created_at": plan.created_at,
                "updated_at": plan.updated_at,
            }
            for plan in plans
        ]

        return {
            "success": True,
            "message": "Subscription plans fetched successfully.",
            "data": formatted_plans
        }
    except SQLAlchemyError as db_err:
        raise HTTPException(status_code=500, detail=f"Database error: {str(db_err)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Something went wrong: {str(e)}")
    
@router.delete("/delete-subscription-plan/{plan_id}")
async def delete_subscription_plan(plan_id: int, request: Request, db: Session = Depends(get_db)):
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
    
# create new subscription plan
@router.post("/create-token-bots", response_model=TokenBotsSchema)
async def create_subscription_plans(data:TokenBotsSchema, request: Request, db: Session = Depends(get_db)):
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

            db.commit()
            db.refresh(existing_plan)
            return existing_plan
        else:
            new_botToken = TokenBots(
                name=data.name,
                pricing=data.pricing,
                token_limits=data.token_limits,
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
            "data": results
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.delete("/delete-token-bot/{token_bot_id}")
async def delete_token_bots(token_bot_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        

        token_bot = db.query(TokenBots).filter(TokenBots.id==token_bot_id).first()
        if token_bot:
            db.delete(token_bot)
            db.commit()
        return {"message": "Token bot deleted successfully"}
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/get-top-consumption-users", response_model=List[User])
async def get_top_consumption_users(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        # get top 10 most token consumption users
        top_users = (
            db.query(AuthUser).filter(AuthUser.tokenUsed != None)
            .order_by(desc(AuthUser.tokenUsed)).limit(10).all()
            )

        return top_users
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# update token bot
@router.put("/update-bot-token", response_model=TokenBotsSchema)
async def update_chatbot(data:TokenBotsSchema, db: Session = Depends(get_db)):
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
async def create_update_bot_product(data:BotProductSchema, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        id = data.id
        if id:
            existing_product = db.query(BotProducts).filter(BotProducts.id == data.id).first()
            if not existing_product:
                raise HTTPException(status_code=404, detail="Product not found")

            existing_product.active = data.active

            db.commit()
            db.refresh(existing_product)
            return existing_product
        else:
            new_bot_product = BotProducts(
                product_name=data.product_name,
                active=data.active
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
            "data": results
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-admin-users", response_model=List[User])
async def get_top_consumption_users(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        # get top 10 most token consumption users
        admins = ["Super Admin", "Billing Admin", "Product Admin", "Support Admin"]
        admin_users = (
            db.query(AuthUser).filter(AuthUser.role.in_(admins)).all()
            )

        return admin_users
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get-client-users", response_model=List[User])
async def get_non_admin_users(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))

        # Define admin roles
        admins = ["Admin","Super Admin", "Billing Admin", "Product Admin", "Support Admin"]

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


    
@router.put("/update-admin-user", response_model=UserUpdate)
async def update_admin_user(data: UserUpdate, request: Request, db: Session = Depends(get_db)):
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
            log_activity="Updated admin user details."
        )
        db.add(log_entry)
        db.commit()

        return existing_user

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/update-client-user", response_model=UserUpdate)
async def update_client_user(data: UserUpdate, request: Request, db: Session = Depends(get_db)):
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
async def delete_admin_user(
    id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
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
                log_activity=f"Deleted user email {adminUser.email}"
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
async def delete_client_user(id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        

        clientUser = db.query(AuthUser).filter(AuthUser.id==id).first()
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
    date_filter: Optional[str] = Query(None, description="Filter up to this date (YYYY-MM-DD)")
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
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        last_added_admin = query.order_by(AuthUser.created_at.desc()).first()
        last_role_updated = query.order_by(AuthUser.updated_at.desc()).first()
        last_suspended_admin = query.filter(AuthUser.status == "Suspend").order_by(AuthUser.updated_at.desc()).first()

        results = {"last_added_admin":last_added_admin, "last_role_updated":last_role_updated, "last_suspended_admin":last_suspended_admin}
       
        return results
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# create update payment gateway
@router.post("/create-update-payment-gateway", response_model=PaymentGatewaySchema)
async def create_update_payment_gateway(data:PaymentGatewaySchema, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        id = data.id
        if id:
            existing_payment = db.query(PaymentGateway).filter(PaymentGateway.id == data.id).first()
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
                payment_name=data.payment_name,
                status=data.status,
                api_key=data.api_key
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
async def delete_payments_gateway(id: int, request: Request, db: Session = Depends(get_db)):
    try:
        token = request.cookies.get("access_token")
        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        payment_gateway = db.query(PaymentGateway).filter(PaymentGateway.id==id).first()
        if payment_gateway:
            db.delete(payment_gateway)
            db.commit()
        return {"message": "Payment gateway deleted successfully!"}
    
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
 

@router.post("/assign", response_model=RolePermissionResponse)
def assign_custom_permissions(data: RolePermissionInput, db: Session = Depends(get_db),current_user: User = Depends(get_current_user)):
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
            log_activity="Updated Permissions for role " + data.role
        )
    db.add(log_entry)
    db.commit()
    return {
        "role": role_obj.role,
        "permissions": role_obj.permissions
    }

    
@router.get("/get", response_model=RolePermissionResponse)
def get_role_permissions(role: str, db: Session = Depends(get_db)):
    role_obj = db.query(RolePermission).filter_by(role=role).first()

    # Predefined system roles that should not throw 404 even if not in DB
    system_roles = {"Super Admin", "Billing Admin", "Product Admin", "Support Admin"}

    if not role_obj:
        if role in system_roles:
            return {
                "role": role,
                "permissions": []  # Return empty by default if not found
            }
        else:
            raise HTTPException(status_code=404, detail="Role not found")

    return {
        "role": role_obj.role,
        "permissions": role_obj.permissions
    }


# @router.get("/get", response_model=RolePermissionResponse)
# def get_role_permissions(role: str, db: Session = Depends(get_db)):
#     role_obj = db.query(RolePermission).filter_by(role=role).first()

#     if not role_obj:
#         raise HTTPException(status_code=404, detail="Role not found")

#     return {
#         "role": role_obj.role,
#         "permissions": role_obj.permissions
#     }

