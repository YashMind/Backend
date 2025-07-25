from fastapi import APIRouter, Depends, HTTPException, Request,Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from sqlalchemy import func, distinct

from decorators.rbac_admin import check_permissions
from models.adminModel.adminModel import SubscriptionPlans
from models.authModel.authModel import AuthUser
from models.chatModel.chatModel import ChatBots
from models.subscriptions.token_usage import TokenUsage, TokenUsageHistory
from models.subscriptions.transactionModel import Transaction
from models.subscriptions.userCredits import HistoryUserCredits, UserCredits
from schemas.chatSchema.tokenAndCreditSchema import (
    UserCreditsAndTokenUsageResponse,
)
from config import get_db
from decorators.product_status import check_product_status
from utils.utils import decode_access_token
from fastapi import HTTPException, Depends
from datetime import datetime


from routes.auth.auth import get_current_user

router = APIRouter()


@router.get("/user-credits", response_model=UserCreditsAndTokenUsageResponse)
@check_product_status("chatbot")
async def get_user_credits_and_tokens(request: Request, db: Session = Depends(get_db)):
    """
    Get user credits and token usage information
    """
    try:
        # Authentication
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Access token missing")

        payload = decode_access_token(token)
        user_id = int(payload.get("user_id"))
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid user ID in token")

        # Get current credits
        credits = db.query(UserCredits).filter_by(user_id=user_id).first()

        # Get token usage
        token_usage = db.query(TokenUsage).filter_by(user_id=user_id).all()

        # Get credit history
        history_credits = (
            db.query(HistoryUserCredits)
            .filter_by(user_id=user_id)
            .order_by(HistoryUserCredits.expiry_date.desc())
            .all()
        )

        return {
            "credits": credits,
            "token_usage": token_usage,
            "history_credits": history_credits,
        }

    except HTTPException as http_exc:
        raise http_exc
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid data format: {str(ve)}")
    except Exception as e:
        # Log the full error for debugging
        print(f"Error in get_user_credits_and_tokens: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while fetching credit information",
        )


@router.get("/token-credit-report")
@check_permissions(["token-analytics"])
async def get_admin_token_credit_report(
    request: Request, page: int = 1, per_page: int = 100, db: Session = Depends(get_db)
):
    try:
        # Authentication - though @check_permissions should handle this already
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Access token missing")

        # This might be redundant if check_permissions already validates the token
        payload = decode_access_token(token)

        # Get current credits with pagination
        credits_query = db.query(UserCredits)
        total_credits = credits_query.count()
        credits = credits_query.offset((page - 1) * per_page).limit(per_page).all()

        # Get associated user IDs from credits
        user_ids = [credit.user_id for credit in credits]

        # Get users in a single query
        users = (
            db.query(AuthUser).filter(AuthUser.id.in_(user_ids)).all()
            if user_ids
            else []
        )
        user_map = {user.id: user for user in users}

        plans = db.query(SubscriptionPlans).all()

        # Get token usage for these users
        token_usage = (
            db.query(TokenUsage)
            .filter(TokenUsage.user_credit_id.in_([c.id for c in credits]))
            .all()
        )

        # Get credit history with pagination
        history_query = db.query(HistoryUserCredits).order_by(
            HistoryUserCredits.expiry_date.desc()
        )
        total_history = history_query.count()
        history_credits = (
            history_query.offset((page - 1) * per_page).limit(per_page).all()
        )

        # Format response with user information
        credit_data = []
        for credit in credits:
            user = user_map.get(credit.user_id)
            credit_data.append(
                {
                    **credit.__dict__,
                    "user": (
                        {
                            "id": user.id if user else None,
                            "email": user.email if user else None,
                            "name": (f"{user.fullName}" if user else None),
                        }
                        if user
                        else None
                    ),
                    "total_token_consumption": next(
                        (
                            usage.combined_token_consumption
                            for usage in token_usage
                            if usage.user_credit_id == credit.id
                        ),
                        0,
                    ),
                    "total_token_consumption_revenue": sum(
                        (
                            usage.combined_token_consumption / credit.token_per_unit
                            for usage in token_usage
                            if usage.user_credit_id == credit.id
                        ),
                        0,
                    ),
                    "token_usage": [
                        usage.__dict__
                        for usage in token_usage
                        if usage.user_credit_id == credit.id
                    ],
                    "plan": next(
                        (plan for plan in plans if plan.id == credit.plan_id), None
                    ),
                }
            )

        return {
            "credits": credit_data,
            "history_credits": [h.__dict__ for h in history_credits],
            "chatbot_revenue": sum(
                (
                    credit.get("total_token_consumption_revenue")
                    for credit in credit_data
                ),
                0,
            ),
            "chatbot_tokens": sum(
                (credit.get("total_token_consumption") for credit in credit_data), 0
            ),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_credits": total_credits,
                "total_history": total_history,
                "total_pages_credits": (total_credits + per_page - 1) // per_page,
                "total_pages_history": (total_history + per_page - 1) // per_page,
            },
        }

    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        # Log the full error for debugging
        print(f"Error in get_admin_token_credit_report: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while fetching credit information",
        )

@router.get("/transactions")
@check_permissions(["billing-settings"])
def get_transactions(
    request: Request, page: int = 1, per_page: int = 100, db: Session = Depends(get_db)
):
    try:
        # Get pagination parameters
        page = max(1, int(request.query_params.get("page", page)))
        per_page = min(100, max(1, int(request.query_params.get("per_page", per_page))))
        
        # Get transactions with pagination
        transactions_query = db.query(Transaction)
        total_transactions = transactions_query.count()
        transactions = (
            transactions_query.order_by(Transaction.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        
        # Calculate total revenue from successful transactions
        # Assuming successful transactions have status like 'completed', 'success', 'paid'
        # Adjust the status values based on your database schema
        successful_statuses = ['completed', 'success', 'paid', 'confirmed']  # Add your success statuses here
        total_revenue = db.query(func.sum(Transaction.amount)).filter(
            Transaction.status.in_(successful_statuses)
        ).scalar() or 0
        
        # Get related user and plan data
        user_ids = {t.user_id for t in transactions if t.user_id}
        plan_ids = {t.plan_id for t in transactions if t.plan_id}
        
        users = (
            db.query(AuthUser).filter(AuthUser.id.in_(user_ids)).all()
            if user_ids
            else []
        )
        user_map = {user.id: user for user in users}
        
        plans = (
            db.query(SubscriptionPlans).filter(SubscriptionPlans.id.in_(plan_ids)).all()
            if plan_ids
            else []
        )
        plan_map = {plan.id: plan for plan in plans}
        
        # Format response
        transaction_data = []
        for transaction in transactions:
            user = user_map.get(transaction.user_id)
            plan = plan_map.get(transaction.plan_id)
            transaction_data.append(
                {
                    "id": transaction.id,
                    "order_id": transaction.order_id,
                    "payment_id": transaction.provider_payment_id,
                    "amount": transaction.amount,
                    "currency": transaction.currency,
                    "status": transaction.status,
                    "payment_method": transaction.payment_method,
                    "created_at": transaction.created_at,
                    "updated_at": transaction.updated_at,
                    "transaction_data": transaction.provider_data,
                    "user": (
                        {
                            "id": user.id if user else None,
                            "email": user.email if user else None,
                            "name": (f"{user.fullName}" if user else None),
                        }
                        if user
                        else None
                    ),
                    "plan": (
                        {
                            "id": plan.id if plan else None,
                            "name": plan.name if plan else None,
                        }
                        if plan
                        else None
                    ),
                }
            )
        
        return {
            "transactions": transaction_data,
            "total_revenue": float(total_revenue),        
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_transactions": total_transactions,
                "total_pages": (total_transactions + per_page - 1) // per_page,
            },
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(ve)}")
    except Exception as e:
        print(f"Error fetching transactions: {str(e)}")
        raise HTTPException(
            status_code=500, detail="An error occurred while fetching transactions"
        )



@router.get("/countries")
def get_country_list(request: Request, db: Session = Depends(get_db)):
    try:
        countries = (
            db.query(AuthUser.country)
            .filter(AuthUser.country.isnot(None))
            .all()
        )
        country_list = [c[0] for c in countries]

        return {"countries": country_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
