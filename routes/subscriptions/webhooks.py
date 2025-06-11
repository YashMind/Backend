import httpx
from models.subscriptions.transactionModel import Transaction
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from config import settings
from config import get_db, settings
import hashlib
import base64
import json
import hmac

from routes.subscriptions.failed_payment import handle_failed_payment
from routes.subscriptions.token_usage import (
    create_token_usage,
    update_token_usage_topup,
)
from routes.subscriptions.transactions import update_transaction
from routes.subscriptions.user_credits import (
    create_user_credit_entry,
    update_user_credit_entry_topup,
)

router = APIRouter()


async def verify_cashfree_webhook(request: Request):
    # Get raw request body as bytes
    raw_body = await request.body()

    print("Raw body: ", raw_body)

    # Extract required headers
    timestamp = request.headers.get("x-webhook-timestamp")
    signature = request.headers.get("x-webhook-signature")

    if not timestamp or not signature:
        raise Exception("Missing required headers")

    # Prepare the signature payload
    signature_data = timestamp.encode("utf-8") + raw_body

    # Get your client secret from Cashfree settings
    secret_key = settings.CASHFREE_SECRET_KEY.encode("utf-8")  # Keep this secure!

    # Generate HMAC-SHA256 signature
    generated_signature = hmac.new(
        key=secret_key, msg=signature_data, digestmod=hashlib.sha256
    ).digest()

    # Base64 encode the signature
    computed_signature = base64.b64encode(generated_signature).decode("utf-8")

    # Compare signatures (use constant-time comparison)
    if not hmac.compare_digest(computed_signature, signature):
        raise Exception("Invalid signature")

    # Parse and return JSON if valid
    return json.loads(raw_body.decode("utf-8"))


async def process_cashfree_payload(payload: dict, db: Session):
    # Extract data from Cashfree payload
    data = payload.get("data", {})
    order = data.get("order", {})
    payment = data.get("payment", {})
    gateway = data.get("payment_gateway_details", {})
    customer = data.get("customer_details", {})

    order_tags = order.get("order_tags")
    transaction_type = order_tags.get("type")

    # Identification parameters
    order_id = order.get("order_id")
    provider_payment_id = gateway.get("gateway_payment_id")
    provider_transaction_id = gateway.get("gateway_order_id")

    # Customer details
    user_id = customer.get("customer_id")

    # Update fields
    payment_status = payment.get("payment_status")
    payment_method = payment.get("payment_group")
    payment_amount = payment.get("payment_amount")
    payment_currency = payment.get("payment_currency")
    payment_method_details = payment.get("payment_method", {})
    fees = payment.get("payment_surcharge")  # Might be None
    # tax = None  # Cashfree doesn't provide tax separately in this payload
    raw_data = payload
    # provider = gateway.get("gateway_name")
    # refund_id = None  # Only present in refund webhooks
    # country_code = "IN"  # Hardcoded or inferred from phone/logic

    print(
        f"ORDER ID: {order_id}, TX STATUS: {payment_status}, PROVIDER TX ID: {provider_transaction_id}"
    )

    # Map status to your schema
    status_map = {
        "SUCCESS": "success",
        "FAILED": "failed",
        "PENDING": "pending",
        "USER_DROPPED": "cancelled",
        "REFUND": "refunded",
    }
    status = status_map.get(payment_status)

    # Update transaction
    transaction = await update_transaction(
        db=db,
        order_id=order_id,
        provider_payment_id=provider_payment_id,
        provider_transaction_id=provider_transaction_id,
        status=status,
        payment_method=payment_method,
        payment_method_details=payment_method_details,
        fees=fees,
        # tax=tax,
        raw_data=raw_data,
        provider="cashfree",
        # refund_id=refund_id,
        # country_code=country_code
    )

    # Add entry in user credits table about updation of plan
    if payload.get("type") == "PAYMENT_SUCCESS_WEBHOOK":

        if transaction_type == "plan":
            user_credit = create_user_credit_entry(trans_id=transaction.id, db=db)

            success, token_entires = create_token_usage(
                credit_id=user_credit.id, transaction_id=transaction.id, db=db
            )

        if transaction_type == "topup":
            user_credit = update_user_credit_entry_topup(trans_id=transaction.id, db=db)

            success, token_entires = update_token_usage_topup(
                credit_id=user_credit.id, transaction_id=transaction.id, db=db
            )

        return {
            "success": success,
            "token_entries": token_entires,
            "details": "payment updated successfully",
        }, 200
    if payload.get("type") == "PAYMENT_FAILED_WEBHOOK":
        # Add payment failed entry in activity logs and support tickets
        handle_failed_payment(transaction_id=transaction.id, raw_data=raw_data, db=db)


async def process_paypal_payload(payload: dict, db: Session):
    print("Received PayPal Payload:", payload)

    resource = payload.get("resource", {})
    event_type = payload.get("event_type", "")
    print(f"Event Type: {event_type}")

    if event_type == "CHECKOUT.ORDER.APPROVED":
        print("Order has been approved by buyer. Attempting to capture payment...")

        # Find the capture link
        capture_link = next(
            (
                link["href"]
                for link in resource.get("links", [])
                if link["rel"] == "capture"
            ),
            None,
        )
        print("Capture link found:", capture_link)

        if not capture_link:
            print("No capture link found in resource.")
            return JSONResponse(
                content={"error": "No capture link found"}, status_code=400
            )

        try:
            # Get PayPal access token
            print("Requesting PayPal access token...")
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    "https://api-m.sandbox.paypal.com/v1/oauth2/token",
                    auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
                    data={"grant_type": "client_credentials"},
                    headers={"Accept": "application/json"},
                )
                token_response.raise_for_status()
                token_data = token_response.json()
                access_token = token_data["access_token"]
                print("Access token retrieved:", access_token)

                # Call the capture endpoint
                print("Calling capture endpoint...")
                capture_response = await client.post(
                    capture_link,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {access_token}",
                    },
                )
                capture_response.raise_for_status()
                capture_result = capture_response.json()
                print("Capture response received:", capture_result)

        except httpx.HTTPError as e:
            print("HTTP Error during capture:", str(e))
            return JSONResponse(
                content={"error": "Capture request failed"}, status_code=500
            )

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        print("Payment has been captured successfully.")
        print(f"Resource: ################# {resource} #################")
        # Now process capture result like PAYMENT.CAPTURE
        status_map = {
            "COMPLETED": "success",
            "DECLINED": "failed",
            "PENDING": "pending",
            "REFUNDED": "refunded",
            "CANCELLED": "cancelled",
        }
        status = status_map.get(resource.get("status"), "unknown")
        print("Mapped status:", status)
        resource = payload.get("resource", {})
        amount_info = resource.get("amount", {})
        breakdown = resource.get("seller_receivable_breakdown", {})

        # Identification parameters
        order_id = (
            resource.get("supplementary_data", {})
            .get("related_ids", {})
            .get("order_id")
        )
        provider_payment_id = resource.get("id")  # Capture ID
        provider_transaction_id = (
            order_id  # Can treat PayPal Order ID as transaction ID
        )

        # Customer/User ID: Not explicitly present, so extract from custom_id or invoice_id if encoded
        transaction_type = resource.get(
            "custom_id"
        )  # You may have encoded this on order creation
        invoice_id = resource.get(
            "invoice_id"
        )  # Invoice ID is locally generated order_id in DB
        user_id = None  # If you encoded user_id in invoice_id or custom_id, parse here

        # Payment info
        payment_status = resource.get("status")
        payment_method = "paypal"
        payment_amount = amount_info.get("value")
        payment_currency = amount_info.get("currency_code")
        payment_method_details = {
            "merchant_email": resource.get("payee", {}).get("email_address"),
            "merchant_id": resource.get("payee", {}).get("merchant_id"),
        }
        fees = breakdown.get("paypal_fee", {}).get("value")

        # Raw data
        raw_data = payload

        transaction = await update_transaction(
            db=db,
            order_id=invoice_id,
            provider_payment_id=provider_payment_id,
            provider_transaction_id=provider_transaction_id,
            status=status,
            payment_method=payment_method,
            payment_method_details=payment_method_details,
            fees=fees,
            # tax=tax,
            raw_data=raw_data,
            provider="paypal",
            # refund_id=refund_id,
            # country_code=country_code
        )

        if transaction_type == "plan":
            user_credit = create_user_credit_entry(trans_id=transaction.id, db=db)

            success, token_entires = create_token_usage(
                credit_id=user_credit.id, transaction_id=transaction.id, db=db
            )

        if transaction_type == "topup":
            user_credit = update_user_credit_entry_topup(trans_id=transaction.id, db=db)

            success, token_entires = update_token_usage_topup(
                credit_id=user_credit.id, transaction_id=transaction.id, db=db
            )

        return {
            "success": success,
            "token_entries": token_entires,
            "details": "payment updated successfully",
        }, 200

    if payload.get("type") in [
        "PAYMENT.CAPTURE.DENIED",
        "PAYMENT.CAPTURE.PENDING",
        "PAYMENT.CAPTURE.REFUNDED",
        "PAYMENT.CAPTURE.REVERSED",
    ]:
        # Add payment failed entry in activity logs and support tickets
        handle_failed_payment(
            order_id=resource.get("invoice_id"), raw_data=raw_data, db=db
        )

    print("Unhandled event type:", event_type)
    return JSONResponse(content={"status": "unhandled_event"}, status_code=200)


# CashFree Webhook Handler
@router.post("/cashfree")
async def cashfree_webhook(request: Request, db: Session = Depends(get_db)):
    try:
        print("CASHFREE PAYLOAD RECIEVED: ", request)
        # Verify signature

        payload = await verify_cashfree_webhook(request=request)
        return await process_cashfree_payload(payload, db)
    except Exception as e:
        print("Error processing CashFree webhook: ", e)
        raise HTTPException(status_code=400, detail=str(e))


# PayPal Webhook Handler
@router.post("/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    # Verify PayPal webhook (implementation depends on PayPal SDK)
    try:
        # This is a placeholder - implement actual verification
        payload = await request.json()
        print(payload)

        return await process_paypal_payload(payload, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
