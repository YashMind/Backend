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
        transaction_type=type,
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


import json
from datetime import datetime, timezone
from fastapi import HTTPException


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
    transaction = None
    try:
        print("🔍 FINDING transaction...")
        if order_id:
            transaction = (
                db.query(Transaction).filter(Transaction.order_id == order_id).first()
            )
            print(f"✅ Transaction found by order_id={order_id}: {transaction}")

        if not transaction and provider_payment_id:
            transaction = (
                db.query(Transaction)
                .filter_by(provider_payment_id=provider_payment_id)
                .first()
            )
            print(
                f"✅ Transaction found by provider_payment_id={provider_payment_id}: {transaction}"
            )

        if not transaction and provider_transaction_id:
            transaction = (
                db.query(Transaction)
                .filter_by(provider_transaction_id=provider_transaction_id)
                .first()
            )
            print(
                f"✅ Transaction found by provider_transaction_id={provider_transaction_id}: {transaction}"
            )

        if not transaction:
            print("❌ No transaction found")
            raise HTTPException(status_code=404, detail="Transaction not found")

        # Provider update
        if provider and transaction.provider != provider:
            print(f"➡ Updating provider: {transaction.provider} -> {provider}")
            transaction.provider = provider

        # Status update
        terminal_states = ["success", "failed", "refunded", "cancelled"]
        if status and status != transaction.status:
            print(f"➡ Updating status: {transaction.status} -> {status}")
            transaction.status = status
            if status in terminal_states:
                transaction.completed_at = datetime.now(timezone.utc)
                print(f"⏱ Completion time set: {transaction.completed_at}")

        # Payment details update
        if payment_method:
            print(
                f"➡ Updating payment_method: {transaction.payment_method} -> {payment_method}"
            )
            transaction.payment_method = payment_method

        if payment_method_details is not None:
            print(
                f"➡ Updating payment_method_details with type={type(payment_method_details)} value={payment_method_details}"
            )
            transaction.payment_method_details = payment_method_details

        if fees is not None:
            print(f"➡ Received fees (dict)={fees}")
            if isinstance(fees, dict):
                # store the total (or pick one value)
                total_fee = fees.get("payment_surcharge_service_charge", 0) + fees.get(
                    "payment_surcharge_service_tax", 0
                )
                print(f"➡ Storing total fees={total_fee}")
                transaction.fees = total_fee
            else:
                transaction.fees = fees

        if tax is not None:
            print(f"➡ Updating tax: {transaction.tax} -> {tax}")
            transaction.tax = tax

        if raw_data is not None:
            print(f"➡ Updating raw_data with type={type(raw_data)} value={raw_data}")
            transaction.provider_data = raw_data

        if country_code:
            print(
                f"➡ Updating country_code: {transaction.country_code} -> {country_code}"
            )
            transaction.country_code = country_code

        if refund_id:
            print(f"➡ Updating refund_id: {transaction.refund_id} -> {refund_id}")
            transaction.refund_id = refund_id

        # Provider IDs
        if provider_transaction_id and not transaction.provider_transaction_id:
            print(f"➡ Setting provider_transaction_id: {provider_transaction_id}")
            transaction.provider_transaction_id = provider_transaction_id
        if provider_payment_id and not transaction.provider_payment_id:
            print(f"➡ Setting provider_payment_id: {provider_payment_id}")
            transaction.provider_payment_id = provider_payment_id

        print("💾 Committing transaction update...")
        db.commit()
        db.refresh(transaction)
        print("✅ Transaction successfully updated:", transaction)
        return transaction

    except Exception as e:
        db.rollback()
        print(f"❌ Transaction update failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Transaction update failed: {str(e)}"
        )
