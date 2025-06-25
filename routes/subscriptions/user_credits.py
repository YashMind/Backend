from datetime import datetime, timedelta
from decimal import Decimal
from fastapi import Depends, HTTPException
from config import get_db
from sqlalchemy.orm import Session

from models.adminModel.adminModel import SubscriptionPlans
from models.subscriptions.transactionModel import Transaction
from models.subscriptions.userCredits import HistoryUserCredits, UserCredits
from models.authModel.authModel import AuthUser as User
from routes.payment.trial_payment import activate_plan


def create_user_credit_entry(
    trans_id: int, db: Session = Depends(get_db), is_trial=False
):
    """Create a user credit entry."""
    # Verify user exists
    # Verify transaction exists
    try:
        transaction = db.query(Transaction).filter(Transaction.id == trans_id).first()
        if not transaction:
            raise HTTPException(status_code=404, detail="Transaction not found")

        user_id = transaction.user_id
        plan_id = transaction.plan_id

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Verify plan exists
        plan = (
            db.query(SubscriptionPlans).filter(SubscriptionPlans.id == plan_id).first()
        )
        if not plan:
            raise HTTPException(status_code=404, detail="Subscription plan not found")

        # Fetch user's current credit entry if exists
        current_credit = (
            db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
        )

        db.query(User).filter(User.id == user.id).update({User.plan: plan.id})

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
                is_trial=current_credit.is_trial,
                expiry_reason="Replaced by new subscription",
            )
            db.add(history_entry)
            db.delete(current_credit)
            db.commit()

        # Calculate expiry date based on plan duration
        start_date = datetime.now()
        expiry_date = start_date + timedelta(days=plan.duration_days)

        if transaction.currency == "USD":
            purchased_credits = (
                Decimal(5 * 100) if is_trial else transaction.amount * Decimal(100)
            )
        else:
            purchased_credits = Decimal(500) if is_trial else transaction.amount

        # Create new credit entry
        new_credit = UserCredits(
            user_id=user_id,
            plan_id=plan_id,
            trans_id=trans_id,
            start_date=start_date,
            expiry_date=expiry_date,
            credits_purchased=purchased_credits,
            credit_balance=purchased_credits,  # Starting balance equals purchased amount
            token_per_unit=plan.token_per_unit,
            chatbots_allowed=plan.chatbots_allowed,
            is_trial=is_trial,
        )

        db.add(new_credit)
        db.commit()
        db.refresh(new_credit)

        activate_plan(user_id=user_id, db=db)

        return new_credit
    except Exception as e:
        print(f"Error updating user credits: {(e)}")
        raise HTTPException(400, "Error updating user credits")


def update_user_credit_entry_topup(trans_id: int, db: Session = Depends(get_db)):
    """Create a user credit entry."""
    print(f"Received top-up request for transaction ID: {trans_id}")

    # Verify transaction exists
    transaction = db.query(Transaction).filter(Transaction.id == trans_id).first()
    if not transaction:
        print("Transaction not found")
        raise HTTPException(status_code=404, detail="Transaction not found")
    print(f"Found transaction: {transaction}")

    # Verify transaction is a top-up
    if transaction.transaction_type != "topup":
        print(f"Invalid transaction type: {transaction.transaction_type}")
        raise HTTPException(status_code=400, detail="Transaction is not a top-up")

    user_id = transaction.user_id
    plan_id = transaction.plan_id
    print(f"Transaction is for user ID: {user_id}, plan ID: {plan_id}")

    # Verify user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        print("User not found")
        raise HTTPException(status_code=404, detail="User not found")
    print(f"Found user: {user}")

    # Verify plan exists
    plan = db.query(SubscriptionPlans).filter(SubscriptionPlans.id == plan_id).first()
    if not plan:
        print("Subscription plan not found")
        raise HTTPException(status_code=404, detail="Subscription plan not found")
    print(f"Found plan: {plan}")

    # Fetch user's current credit entry
    current_credit = (
        db.query(UserCredits).filter(UserCredits.user_id == user_id).first()
    )
    if not current_credit:
        print("No existing credit entry found for user")
        raise HTTPException(status_code=404, detail="Credit entry not found")
    print(f"Current credit entry: {current_credit}")

    if any(tx.id == trans_id for tx in current_credit.top_up_transactions):
        print(f"Transaction ID {trans_id} already exists in user's top-up transactions")
        return current_credit

    if trans_id == current_credit.trans_id:
        print("Credit entry already updated under the same transaction")
        return current_credit

    if current_credit.expiry_date < datetime.now():
        print("Plan has already expired on:", current_credit.expiry_date)
        return current_credit

    new_credits = Decimal(transaction.amount)
    if transaction.currency == "USD":
        new_credits = Decimal(new_credits * 100)
    print(f"Calculated new credits: {new_credits}")

    current_credit.credits_purchased += new_credits
    current_credit.credit_balance = (
        current_credit.credits_purchased - current_credit.credits_consumed
    )
    current_credit.top_up_transactions.append(transaction)
    print(f"Updated credit entry: {current_credit}")

    db.add(current_credit)
    db.commit()
    print("Credit entry successfully updated and committed")

    return current_credit
