"""Real Stripe checkout, signed events, and explicit cash settlement."""

import hashlib
import hmac
import json
import time
from datetime import timezone
from decimal import Decimal

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.catalogue import get_record, serialize
from app.config import get_settings
from app.database import audit, utcnow
from app.models import Order, Payment, PaymentEvent
from app.orders import transition, visible_order
from app.schemas import PaymentInput


def initiate_payment(
    db: Session, actor: Principal, data: PaymentInput
) -> dict:
    """Create a provider checkout session without marking an order paid."""
    visible_order(db, actor, data.order_id)
    order = db.scalar(
        select(Order).where(Order.id == data.order_id).with_for_update()
    )
    if order.status != "pending_payment" or order.expires_at <= utcnow():
        raise HTTPException(409, "Order no longer accepts payment")
    existing = db.scalar(
        select(Payment).where(
            Payment.order_id == order.id,
            Payment.method == data.method,
            Payment.status.in_(["pending", "initializing"]),
        )
    )
    if existing:
        return serialize(existing)
    if data.method == "stripe" and not get_settings().stripe_secret_key:
        raise HTTPException(503, "Stripe is not configured")
    payment = Payment(
        order_id=order.id,
        method=data.method,
        amount=order.total,
        currency=order.currency,
        status="initializing" if data.method == "stripe" else "pending",
    )
    db.add(payment)
    db.flush()
    audit(db, actor.id, "payment.initiate", payment.id)
    return serialize(payment)


def create_stripe_session(payment: Payment, order: Order) -> None:
    """Request a hosted card checkout using a stable idempotency key."""
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise HTTPException(503, "Stripe is not configured")
    if order.currency not in {"USD", "EUR", "GBP", "RWF"}:
        raise HTTPException(422, "Currency needs a configured minor-unit rule")
    multiplier = 1 if order.currency == "RWF" else 100
    amount = payment.amount * multiplier
    if amount != amount.to_integral_value():
        raise HTTPException(422, "Amount has unsupported currency precision")
    payload = {
        "mode": "payment",
        "client_reference_id": payment.id,
        "metadata[payment_id]": payment.id,
        "success_url": settings.public_url + "/?payment=returned",
        "cancel_url": settings.public_url + "/?payment=cancelled",
        "line_items[0][price_data][currency]": order.currency.lower(),
        "line_items[0][price_data][unit_amount]": str(int(amount)),
        "line_items[0][price_data][product_data][name]": f"Order {order.id}",
        "line_items[0][quantity]": "1",
        "expires_at": str(
            int(order.expires_at.replace(tzinfo=timezone.utc).timestamp())
        ),
    }
    result = stripe_request("checkout/sessions", payload, payment.id)
    payment.reference = result["id"]
    payment.checkout_url = result["url"]
    payment.status = "pending"


def stripe_request(path: str, payload: dict, key: str) -> dict:
    """Use authenticated HTTPS with timeouts and safe provider errors."""
    settings = get_settings()
    try:
        response = httpx.post(
            "https://api.stripe.com/v1/" + path,
            data=payload,
            auth=(settings.stripe_secret_key, ""),
            headers={"Idempotency-Key": key},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(502, "Payment provider unavailable") from error


def verify_stripe_signature(body: bytes, signature: str) -> dict:
    """Authenticate the exact raw bytes with replay-window enforcement."""
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise HTTPException(503, "Payment webhook is not configured")
    try:
        fields = [item.split("=", 1) for item in signature.split(",")]
        timestamp = next(value for key, value in fields if key == "t")
        expected = hmac.new(
            secret.encode(),
            timestamp.encode() + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        valid = any(
            key == "v1" and hmac.compare_digest(value, expected)
            for key, value in fields
        )
        if not valid or abs(time.time() - int(timestamp)) > 300:
            raise ValueError("Invalid signature")
        return json.loads(body)
    except (ValueError, StopIteration) as error:
        raise HTTPException(401, "Invalid payment signature") from error


def payment_event(db: Session, event: dict) -> dict:
    """Apply verified Stripe events idempotently after amount checks."""
    event_type = event.get("type", "")
    if event_type in {"refund.updated", "refund.created", "refund.failed"}:
        return refund_event(db, event)
    supported = {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
        "checkout.session.expired",
    }
    if event_type not in supported:
        return {"received": True, "ignored": True}
    data = event.get("data", {}).get("object", {})
    payment_id = data.get("metadata", {}).get("payment_id", "")
    payment = db.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if not payment or payment.reference != data.get("id"):
        raise HTTPException(422, "Unknown payment reference")
    if db.get(PaymentEvent, event["id"]):
        return {"received": True, "duplicate": True}
    validate_event_amount(payment, data)
    db.add(PaymentEvent(id=event["id"], payment_id=payment.id))
    if data.get("payment_status") == "paid":
        settle_payment(db, payment, "stripe")
    elif event_type.endswith(("failed", "expired")):
        if payment.status in {"initializing", "pending"}:
            payment.status = "failed"
    return {"received": True}


def refund_event(db, event: dict) -> dict:
    """Track asynchronous provider refunds using signed metadata."""
    data = event.get("data", {}).get("object", {})
    payment_id = data.get("metadata", {}).get("payment_id", "")
    payment = db.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if not payment:
        raise HTTPException(422, "Unknown refund payment")
    if db.get(PaymentEvent, event["id"]):
        return {"received": True, "duplicate": True}
    validate_event_amount(
        payment,
        {
            "amount_total": data.get("amount"),
            "currency": data.get("currency"),
        },
    )
    db.add(PaymentEvent(id=event["id"], payment_id=payment.id))
    if data.get("status") == "succeeded":
        order = db.scalar(
            select(Order).where(Order.id == payment.order_id).with_for_update()
        )
        if order.status == "refund_pending":
            transition(db, order, "refunded", "stripe")
        payment.status = "refunded"
    elif (
        data.get("status") in {"failed", "canceled"}
        and payment.status != "refunded"
    ):
        payment.status = "paid"
        audit(db, "stripe", "refund.failed", payment.id)
    return {"received": True}


def validate_event_amount(payment: Payment, data: dict) -> None:
    """Reject callbacks that disagree with the server's monetary snapshot."""
    multiplier = 1 if payment.currency == "RWF" else 100
    amount = Decimal(str(data.get("amount_total", -1)))
    if amount != payment.amount * multiplier:
        raise HTTPException(422, "Payment amount mismatch")
    if data.get("currency", "").upper() != payment.currency:
        raise HTTPException(422, "Payment currency mismatch")


def settle_payment(db: Session, payment: Payment, actor_id: str) -> None:
    """Record real settlement, flagging late and duplicate payments."""
    if payment.status in {"paid", "refunded", "refund_pending"}:
        return
    order = db.scalar(
        select(Order).where(Order.id == payment.order_id).with_for_update()
    )
    payment.status = "paid"
    if order.status == "pending_payment":
        transition(db, order, "paid", actor_id)
    elif order.status in {"expired", "cancelled"}:
        order.status = "refund_pending"
        audit(db, actor_id, "payment.late_refund_required", order.id)
    else:
        audit(db, actor_id, "payment.review_settlement", payment.id)
    audit(db, actor_id, "payment.paid", payment.id)


def settle_cash(db: Session, actor: Principal, payment_id: str) -> dict:
    """Record staff-confirmed receipt of cash, never checkout intent."""
    actor.require("payments.write")
    payment = db.scalar(
        select(Payment).where(Payment.id == payment_id).with_for_update()
    )
    if not payment or payment.method != "cash":
        raise HTTPException(404, "Cash payment not found")
    settle_payment(db, payment, actor.id)
    return serialize(payment)


def refund_payment(db: Session, actor: Principal, payment_id: str) -> dict:
    """Refund a settled Stripe payment through the provider API."""
    actor.require("payments.write")
    payment = get_record(db, Payment, payment_id)
    order = get_record(db, Order, payment.order_id)
    if payment.method != "stripe" or payment.status != "paid":
        raise HTTPException(409, "Only settled Stripe payments are refundable")
    if order.status != "refund_pending":
        raise HTTPException(409, "Move the order to refund pending first")
    settings = get_settings()
    try:
        response = httpx.get(
            "https://api.stripe.com/v1/checkout/sessions/" + payment.reference,
            auth=(settings.stripe_secret_key, ""),
            timeout=20,
        )
        response.raise_for_status()
        intent = response.json()["payment_intent"]
    except (httpx.HTTPError, KeyError) as error:
        raise HTTPException(502, "Cannot retrieve payment") from error
    result = stripe_request(
        "refunds",
        {"payment_intent": intent, "metadata[payment_id]": payment.id},
        "refund-" + payment.id,
    )
    payment.status = (
        "refunded" if result["status"] == "succeeded" else ("refund_pending")
    )
    if payment.status == "refunded":
        transition(db, order, "refunded", actor.id)
    return serialize(payment)
