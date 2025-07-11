import random
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
import requests
import hmac
import hashlib
import json
import os
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime
from config import get_db
from models.adminModel.adminModel import SubscriptionPlans
from models.authModel.authModel import AuthUser
from models.paymentModel.paymentModel import (
    PaymentVerificationRequest,
    PaymentOrderRequest,
)
from sqlalchemy.orm import Session
from models.subscriptions.userCredits import UserCredits
from routes.subscriptions.transactions import create_transaction
from utils.utils import get_country_from_ip

router = APIRouter()
load_dotenv()

# Configuration
CASHFREE_ENV = os.getenv("CASHFREE_ENV", "TEST")
CASHFREE_APP_ID = os.getenv("CASHFREE_APP_ID")
CASHFREE_SECRET_KEY = os.getenv("CASHFREE_SECRET_KEY")
CASHFREE_API_VERSION = os.getenv("CASHFREE_API_VERSION", "2023-08-01")
CASHFREE_BASE_URL = (
    f"https://{'sandbox' if CASHFREE_ENV == 'TEST' else 'api'}.cashfree.com/pg"
)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

notify_url = (
    "https://yashraa.ai/api/webhook/payments/cashfree"
    if CASHFREE_ENV == "TEST"
    else "https://yashraa.ai/webhook/payments/cashfree"
)


def generate_cashfree_auth_headers():
    """Generate headers for Cashfree API requests"""
    if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
        raise ValueError("Cashfree credentials not properly configured")

    return {
        "x-client-id": CASHFREE_APP_ID,
        "x-client-secret": CASHFREE_SECRET_KEY,
        "x-api-version": CASHFREE_API_VERSION,
        "Content-Type": "application/json",
    }


def generate_order_id() -> str:
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    return f"cf_{timestamp_ms}_{random.randint(0, 999)}"


@router.post("/create-order")
async def create_payment_order(
    request: Request, order_data: PaymentOrderRequest, db: Session = Depends(get_db)
):
    """Create a payment order in Cashfree"""
    url = f"{CASHFREE_BASE_URL}/orders"
    client_ip = request.client.host
    # Validate environment variables
    if not CASHFREE_APP_ID or not CASHFREE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cashfree credentials not configured",
        )

    # Debug prints
    print(
        f"Cashfree Configuration - App ID: {CASHFREE_APP_ID}, Env: {CASHFREE_ENV}, API Version: {CASHFREE_API_VERSION}"
    )

    user = db.query(AuthUser).filter(AuthUser.id == order_data.customer_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")

    amount = 0
    plan_id = None
    type = None
    country = await get_country_from_ip(ip=client_ip)
    currency = "USD"

    print("Country: ", country)
    if order_data.plan_id:
        plan = (
            db.query(SubscriptionPlans)
            .filter(SubscriptionPlans.id == order_data.plan_id)
            .first()
        )

        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        amount = plan.pricingDollar

        if country == "IN":
            amount = plan.pricingInr
            currency = "INR"
        plan_id = plan.id
        type = "plan"

    if order_data.credit:
        amount = order_data.credit

        type = "topup"
        if country == "IN":
            currency = "INR"

        credit = db.query(UserCredits).filter_by(user_id=user.id).first()
        if not credit:
            raise HTTPException(status_code=404, detail="No plan found")

        if credit.expiry_date < datetime.now():
            raise HTTPException(
                status_code=404,
                detail="Current plan is expired. No active plan to add credits",
            )

        plan_id = credit.plan_id

    if not (order_data.plan_id or order_data.credit):
        raise HTTPException(
            status_code=400, detail="Either plan_id or credit must be provided"
        )

    payload = {
        "order_id": generate_order_id(),
        "order_amount": amount,
        "order_currency": currency,
        "customer_details": {
            "customer_id": str(order_data.customer_id),
            "customer_name": user.fullName,
            "customer_email": user.email,
            "customer_phone": "9875905950",
        },
        "order_meta": {
            "return_url": order_data.return_url,
            "notify_url": notify_url,
        },
        "order_tags": {"type": type},
    }

    print("Creating order with payload:", json.dumps(payload, indent=2))

    headers = generate_cashfree_auth_headers()

    try:
        response = requests.post(url, json=payload, headers=headers)

        print(f"Cashfree Response Status: {response.status_code}")
        print(f"Cashfree Response Body: {response.text}")

        if response.status_code != 200:
            print(f"Cashfree API Error: {response.status_code} - {response.text}")

            # Try to parse error response
            try:
                error_data = response.json()
                error_message = error_data.get("message", "Cashfree API request failed")
                error_code = error_data.get("code", "UNKNOWN")

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": error_message,
                        "code": error_code,
                        "status_code": response.status_code,
                    },
                )
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "message": "Cashfree API request failed",
                        "status_code": response.status_code,
                        "response": response.text,
                    },
                )

        cashfree_response = response.json()

        # Enhanced validation
        if "payment_session_id" not in cashfree_response:
            print(f"Invalid Cashfree response: {cashfree_response}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Cashfree did not return a valid session ID",
            )

        print("CASHFREE RESPONSE: ", cashfree_response)
        new_transaction = await create_transaction(
            db=db,
            provider="cashfree",
            order_id=cashfree_response["order_id"],
            user_id=int(cashfree_response["customer_details"]["customer_id"]),
            amount=cashfree_response["order_amount"],
            currency=cashfree_response["order_currency"],
            type=cashfree_response["order_tags"]["type"],
            plan_id=plan_id,
            status="pending",
        )

        # Return the complete response for frontend handling
        return {
            "success": True,
            "payment_session_id": cashfree_response["payment_session_id"],
            "order_id": cashfree_response["order_id"],
            "cf_order_id": cashfree_response.get("cf_order_id"),
            "order_amount": cashfree_response["order_amount"],
            "order_status": cashfree_response.get("order_status"),
            "message": "Order created successfully",
        }

    except requests.exceptions.HTTPError as e:
        error_detail = {
            "error": str(e),
            "response_text": e.response.text if e.response else None,
            "status_code": e.response.status_code if e.response else None,
        }
        print("HTTP Error:", json.dumps(error_detail, indent=2))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Failed to create payment order",
                "details": error_detail,
            },
        )
    except requests.exceptions.RequestException as e:
        print("Request Exception:", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Network error while creating payment order: {str(e)}",
        )
    except Exception as e:
        print("Unexpected error:", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/verify-payment")
async def verify_payment(verification_data: PaymentVerificationRequest):
    """Verify payment status with Cashfree"""
    url = f"{CASHFREE_BASE_URL}/orders/{verification_data.order_id}/payments"
    if verification_data.payment_id:
        url += f"/{verification_data.payment_id}"

    headers = generate_cashfree_auth_headers()

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        payment_data = response.json()

        # For single payment ID verification
        if verification_data.payment_id:
            return {"status": "SUCCESS", "payment_data": payment_data}

        # For order ID verification (multiple payments possible)
        payments = payment_data.get("payments", [])
        if not payments:
            return {"status": "PENDING", "message": "No payments found for this order"}

        # Return the most recent payment
        latest_payment = max(payments, key=lambda x: x.get("payment_time", ""))
        return {"status": "SUCCESS", "payment_data": latest_payment}
    except requests.exceptions.RequestException as e:
        error_detail = {
            "error": str(e),
            "response_text": e.response.text if e.response else None,
            "status_code": e.response.status_code if e.response else None,
        }
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Failed to verify payment", "details": error_detail},
        )


def verify_webhook_signature(payload: bytes, signature: str):
    """Verify Cashfree webhook signature"""
    if not WEBHOOK_SECRET:
        raise ValueError("Webhook secret not configured")

    computed_signature = hmac.new(
        WEBHOOK_SECRET.encode(), msg=payload, digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed_signature, signature)


@router.get("/is-international")
async def is_international(request: Request):
    try:
        client_ip = request.client.host
        print(f"Client IP: {client_ip}")
        country = await get_country_from_ip(ip=client_ip)
        print("Country", country)
        if country == "IN":
            return {"is_international": False}

        return {"is_international": True}
    except Exception as e:
        print(f"Error: {e}")
