import random
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
import requests
import json
from dotenv import load_dotenv
from typing import Optional
from datetime import datetime
from models.adminModel.adminModel import SubscriptionPlans
from models.authModel.authModel import AuthUser
from models.paymentModel.paymentModel import PaymentOrderRequest
from paypalcheckoutsdk.orders import OrdersCreateRequest
from models.subscriptions.userCredits import UserCredits
from routes.payment.paypal_service import PayPalClient
from routes.subscriptions.transactions import create_transaction
from utils.utils import get_country_from_ip
from config import get_db, settings

router = APIRouter()
load_dotenv()


# @router.post("/create-paypal-order")
# async def create_paypal_order(order_request: OrderRequest):
#     try:
#         print("Received order request:", order_request)

#         request = OrdersCreateRequest()
#         request.prefer("return=representation")

#         total = sum(
#             float(item.price) * float(item.quantity) for item in order_request.items
#         )
#         print("Calculated total:", total)

#         request_body = {
#             "intent": "CAPTURE",
#             "application_context": {
#                 "return_url": order_request.return_url,
#                 "cancel_url": order_request.cancel_url,
#                 "brand_name": "Your Brand Name",
#                 "user_action": "PAY_NOW",
#             },
#             "purchase_units": [
#                 {
#                     "items": [
#                         {
#                             "name": item.name,
#                             "description": item.description,
#                             "quantity": item.quantity,
#                             "unit_amount": {
#                                 "currency_code": item.currency,
#                                 "value": item.price,
#                             },
#                         }
#                         for item in order_request.items
#                     ],
#                     "amount": {
#                         "currency_code": order_request.items[0].currency,
#                         "value": str(total),
#                         "breakdown": {
#                             "item_total": {
#                                 "currency_code": order_request.items[0].currency,
#                                 "value": str(total),
#                             }
#                         },
#                     },
#                 }
#             ],
#         }

#         print("Request body prepared:", request_body)

#         request.request_body(request_body)

#         client = PayPalClient()
#         print("Executing PayPal order request...")
#         response = client.client.execute(request)

#         print("PayPal response status:", response.status_code)
#         print("PayPal response result:", response.result)

#         for link in response.result.links:
#             print(f"Link: {link.rel} -> {link.href}")
#             if link.rel == "approve":
#                 return {"orderID": response.result.id, "approveUrl": link.href}

#         raise HTTPException(status_code=400, detail="Failed to create PayPal order")

#     except Exception as e:
#         print("Exception occurred:", str(e))
#         raise HTTPException(status_code=500, detail=str(e))


def generate_order_id() -> str:
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    return f"pp_{timestamp_ms}_{random.randint(0, 999)}"


@router.post("/create-paypal-order")
async def create_paypal_order(
    request: Request,
    order_data: PaymentOrderRequest,
    db: requests.Session = Depends(get_db),
):
    """Create a PayPal payment order"""
    print("Received request to create PayPal order")

    if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
        print("PayPal credentials missing in settings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PayPal credentials not configured",
        )

    client_ip = request.client.host
    print(f"Client IP: {client_ip}")

    country = await get_country_from_ip(ip=client_ip)
    print(f"Detected country from IP: {country}")

    user = db.query(AuthUser).filter(AuthUser.id == order_data.customer_id).first()
    if not user:
        print(f"User not found: {order_data.customer_id}")
        raise HTTPException(status_code=404, detail="Customer not found")

    amount = 0
    plan_id = None
    transaction_type = None
    currency = "USD"

    if order_data.plan_id:
        print(f"Fetching subscription plan: {order_data.plan_id}")
        plan = (
            db.query(SubscriptionPlans)
            .filter(SubscriptionPlans.id == order_data.plan_id)
            .first()
        )
        if not plan:
            print("Plan not found")
            raise HTTPException(status_code=404, detail="Plan not found")

        amount = plan.pricingDollar
        if country == "IN":
            amount = plan.pricingInr
            currency = "INR"
        plan_id = plan.id
        transaction_type = "plan"
        print(f"Plan selected. Amount: {amount}, Currency: {currency}")

    elif order_data.credit:
        print(f"Processing credit top-up: {order_data.credit}")
        amount = order_data.credit
        transaction_type = "topup"
        if country == "IN":
            currency = "INR"

        credit = db.query(UserCredits).filter_by(user_id=user.id).first()
        if not credit:
            print("No credit plan found")
            raise HTTPException(status_code=404, detail="No credit plan found")
        if credit.expiry_date < datetime.now():
            print("Credit plan expired")
            raise HTTPException(
                status_code=400,
                detail="Current plan expired. Cannot add credits",
            )
        plan_id = credit.plan_id
        print(f"Top-up allowed under credit plan ID: {plan_id}")

    else:
        print("Neither plan_id nor credit provided in request")
        raise HTTPException(
            status_code=400, detail="Either plan_id or credit must be provided"
        )

    paypal_request = OrdersCreateRequest()
    paypal_request.prefer("return=representation")

    request_body = {
        "intent": "CAPTURE",
        "application_context": {
            "return_url": order_data.return_url,
            "cancel_url": settings.PAYPAL_CANCEL_URL,
            "brand_name": "Your Brand Name",
            "user_action": "PAY_NOW",
        },
        "purchase_units": [
            {
                "invoice_id": generate_order_id(),  # Order_ID
                "reference_id": order_data.customer_id,  # Customer_ID
                "custom_id": transaction_type,  # Transaction_Type
                "description": f"{'Subscription Plan' if transaction_type == 'plan' else 'Credit Top-up'}",
                "amount": {
                    "currency_code": currency,
                    "value": f"{amount:.2f}",
                },
            }
        ],
    }

    print("Creating PayPal order with payload:")
    print(json.dumps(request_body, indent=2))

    paypal_request.request_body(request_body)

    try:
        print("Initializing PayPal client...")
        client = PayPalClient()
        response = client.client.execute(paypal_request)

        print(f"PayPal response status: {response.status_code}")
        if response.status_code != 201:
            print("PayPal API error:", response.result.details)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PayPal API error: {response.result.details[0].description}",
            )

        approval_url = next(
            (link.href for link in response.result.links if link.rel == "approve"), None
        )
        if not approval_url:
            print("No approval URL found in PayPal response")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No approval URL found in PayPal response",
            )

        paypal_order_id = response.result.id
        paypal_order_result = response.result
        print(f"PayPal Order ID: {paypal_order_id}")
        print(f"Approval URL: {approval_url}")
        print(
            "Paypal Order:", json.dumps(response.result.__dict__, indent=2, default=str)
        )

        await create_transaction(
            db=db,
            provider="paypal",
            provider_transaction_id=paypal_order_id,
            order_id=paypal_order_result.purchase_units[0].invoice_id,
            user_id=int(
                paypal_order_result.purchase_units[0].reference_id
                or order_data.customer_id
            ),
            amount=amount,
            currency=currency,
            type=paypal_order_result.purchase_units[0].custom_id or transaction_type,
            plan_id=plan_id,
            status="pending",
        )

        print("Transaction record created")

        return {
            "success": True,
            "order_id": paypal_order_id,
            "approve_url": approval_url,
            "message": "PayPal order created successfully",
        }

    except HTTPException as he:
        print(f"HTTPException: {he.detail}")
        raise he
    except Exception as e:
        print(f"Unhandled exception during PayPal order creation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PayPal order creation failed: {str(e)}",
        )


@router.post("/capture-paypal-order/{order_id}")
async def capture_paypal_order(order_id: str):
    try:
        from paypalcheckoutsdk.orders import OrdersCaptureRequest

        request = OrdersCaptureRequest(order_id)
        client = PayPalClient()
        response = client.client.execute(request)

        if response.result.status == "COMPLETED":
            return {
                "status": "success",
                "orderID": order_id,
                "details": response.result,
            }
        else:
            raise HTTPException(status_code=400, detail="Payment not completed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
