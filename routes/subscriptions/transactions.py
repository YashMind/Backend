from config import get_db
from models.subscriptions.transactionModel import Transaction
from fastapi import Depends, HTTPException
from datetime import datetime, timezone
from sqlalchemy.orm import Session


async def create_transaction(
    # Required fields
    provider: str,
    order_id: str,
    user_id: int,
    amount: float,
    currency: str,
    type: str,
    # Optional fields
    plan_id: int = None,
    provider_payment_id: str = None,
    provider_transaction_id: str = None,
    status: str = "created",
    payment_method: str = None,
    payment_method_details: dict = None,
    fees: float = None,
    tax: float = None,
    raw_data: dict = None,
    country_code: str = None,
    db: Session = Depends(get_db),
):
    # Check if transaction already exists
    existing = db.query(Transaction).filter_by(order_id=order_id).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Transaction with order_id {order_id} already exists",
        )

    # Create new transaction
    transaction = Transaction(
        provider=provider,
        order_id=order_id,
        user_id=user_id,
        plan_id=plan_id,
        amount=amount,
        currency=currency,
        type=type,
        provider_payment_id=provider_payment_id,
        provider_transaction_id=provider_transaction_id,
        status=status,
        payment_method=payment_method,
        payment_method_details=payment_method_details,
        fees=fees,
        tax=tax,
        provider_data=raw_data,
        country_code=country_code,
        created_at=datetime.now(timezone.utc),
    )
    # Set completion time if initial state is terminal
    terminal_states = ["success", "failed", "refunded", "cancelled"]
    if status in terminal_states:
        transaction.completed_at = datetime.now(timezone.utc)

    try:
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        return transaction
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Transaction creation failed: {str(e)}"
        )


async def update_transaction(
    db: Session,
    # Identification parameters (at least one required)
    order_id: str = None,
    provider_payment_id: str = None,
    provider_transaction_id: str = None,
    # Update fields
    status: str = None,
    payment_method: str = None,
    payment_method_details: dict = None,
    fees: float = None,
    tax: float = None,
    raw_data: dict = None,
    provider: str = None,
    refund_id: str = None,
    country_code: str = None,
):
    # Find transaction using available identifiers
    transaction = None

    print("FINDING transaction from order id")
    if order_id:
        transaction = (
            db.query(Transaction).filter(Transaction.order_id == order_id).first()
        )
        print("Transaction found from order_id", transaction)

    if not transaction and provider_payment_id:
        transaction = (
            db.query(Transaction)
            .filter_by(provider_payment_id=provider_payment_id)
            .first()
        )
    if not transaction and provider_transaction_id:
        transaction = (
            db.query(Transaction)
            .filter_by(provider_transaction_id=provider_transaction_id)
            .first()
        )

    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    # Update provider if needed
    if provider and transaction.provider != provider:
        transaction.provider = provider

    # Update status if provided
    terminal_states = ["success", "failed", "refunded", "cancelled"]
    if status and status != transaction.status:
        transaction.status = status
        # Set completion time for terminal states
        if status in terminal_states:
            transaction.completed_at = datetime.now(timezone.utc)

    # Update payment details
    if payment_method:
        transaction.payment_method = payment_method
    if payment_method_details is not None:
        transaction.payment_method_details = payment_method_details
    if fees is not None:
        transaction.fees = fees
    if tax is not None:
        transaction.tax = tax
    if raw_data is not None:
        transaction.provider_data = raw_data
    if country_code:
        transaction.country_code = country_code
    if refund_id:
        transaction.refund_id = refund_id

    # Update provider IDs if missing
    if provider_transaction_id and not transaction.provider_transaction_id:
        transaction.provider_transaction_id = provider_transaction_id
    if provider_payment_id and not transaction.provider_payment_id:
        transaction.provider_payment_id = provider_payment_id

    try:
        db.commit()
        db.refresh(transaction)
        return transaction
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Transaction update failed: {str(e)}"
        )
