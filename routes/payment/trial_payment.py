from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Request, status
from requests import Session

from config import get_db
from models.adminModel.adminModel import SubscriptionPlans
from models.authModel.authModel import AuthUser
from models.subscriptions.token_usage import TokenUsage
from models.subscriptions.userCredits import UserCredits
from routes.subscriptions.transactions import create_transaction
from pydantic import BaseModel

from schemas.authSchema.authSchema import User


class TrialOrderRequest(BaseModel):
    plan_id: str
    user_id: str


async def create_trial_order(
    trial_data: TrialOrderRequest,  # You'll need to create this Pydantic model
    db: Session = Depends(get_db),
):
    """Create a trial order (no payment required)"""
    try:
        user = (
            db.query(AuthUser).filter(AuthUser.id == trial_data.get("user_id")).first()
        )
        if not user:
            raise HTTPException(status_code=404, detail="Customer not found")

        print("Subscription Plan: ", trial_data.get("plan_id"))
        # Validate trial plan exists
        trial_plan = (
            db.query(SubscriptionPlans)
            .filter(
                SubscriptionPlans.id == trial_data.get("plan_id"),
                SubscriptionPlans.is_trial == True,
            )
            .first()
        )

        if not trial_plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Trial plan not found"
            )

        # Create trial order ID
        order_id = f"trial_{user.id}_{datetime.now().timestamp()}"
        print("creating transaction")
        # Create transaction record
        new_transaction = await create_transaction(
            db=db,
            provider="trial",
            order_id=order_id,
            user_id=user.id,
            amount=0,
            currency="USD",
            type="trial",
            plan_id=trial_plan.id,
            status="success",
        )
        print("transaction Created")

        return new_transaction

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating trial order: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to activate trial",
        )


def has_activated_plan(user_id: str, db: Session = Depends(get_db)):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if user.activate_plan:
            return True
        else:
            return False
    except Exception as e:
        print(f"Error checking for active trial: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check for active trial",
        )


def activate_plan(user_id: str, db: Session = Depends(get_db)):
    try:
        user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        user.activate_plan = True
        db.commit()
    except Exception as e:
        print(f"Error while activating plan: {str(e)}")
