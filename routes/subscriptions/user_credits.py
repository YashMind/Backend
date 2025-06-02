from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from config import get_db
from sqlalchemy.orm import Session

from models.adminModel.adminModel import SubscriptionPlans
from models.subscriptions.transactionModel import Transaction
from models.subscriptions.userCredits import HistoryUserCredits, UserCredits
from models.authModel.authModel import AuthUser as User


def create_user_credit_entry(trans_id: int, db: Session = Depends(get_db)):
    """Create a user credit entry."""
    # Verify user exists
    # Verify transaction exists
    transaction = db.query(Transaction).filter(Transaction.id == trans_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    user_id = transaction.user_id
    plan_id = transaction.plan_id

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify plan exists
    plan = db.query(SubscriptionPlans).filter(SubscriptionPlans.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Subscription plan not found")

    # Fetch user's current credit entry if exists
    current_credit = (
        db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
    )

    if current_credit and trans_id == current_credit.trans_id:
        print("Credit entry already updated under same transaction")
        return current_credit

    if current_credit and trans_id != current_credit.trans_id:
        # Move current entry to history before creating new one
        history_entry = HistoryUserCredits(
            user_id=current_credit.user_id,
            trans_id=current_credit.trans_id,
            plan_id=current_credit.plan_id,
            start_date=current_credit.start_date,
            expiry_date=current_credit.expiry_date,
            credits_purchased=current_credit.credits_purchased,
            credits_consumed=current_credit.credits_consumed,
            credit_balance=current_credit.credit_balance,
            token_per_unit=current_credit.token_per_unit,
            chatbots_allowed=current_credit.chatbots_allowed,
            expiry_reason="Replaced by new subscription",
        )
        db.add(history_entry)
        db.delete(current_credit)
        db.commit()

    # Calculate expiry date based on plan duration
    start_date = datetime.now()
    expiry_date = start_date + timedelta(days=plan.duration_days)

    # Create new credit entry
    new_credit = UserCredits(
        user_id=user_id,
        plan_id=plan_id,
        trans_id=trans_id,
        start_date=start_date,
        expiry_date=expiry_date,
        credits_purchased=transaction.amount,
        credit_balance=transaction.amount,  # Starting balance equals purchased amount
        token_per_unit=plan.token_per_unit,
        chatbots_allowed=plan.chatbots_allowed,
    )

    db.add(new_credit)
    db.commit()
    db.refresh(new_credit)

    return new_credit
