"""Bounded durable inbox/outbox processing without another service."""

import asyncio
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.database import SessionLocal, utcnow
from app.models import Customer, Notification, Order, Payment, WebhookJob
from app.notices import queue_text
from app.orders import transition
from app.payments import create_stripe_session
from app.whatsapp import process_message, send_message

logger = logging.getLogger(__name__)


def process_one(model, handler) -> None:
    """Lock one due job and persist retry state independently of its work."""
    with SessionLocal.begin() as db:
        job = db.scalar(
            select(model)
            .where(model.status == "pending", model.next_attempt <= utcnow())
            .order_by(model.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return
        job.attempts += 1
        try:
            with db.begin_nested():
                handler(db, job)
            job.status = "sent" if model == Notification else "processed"
            job.error = ""
        except Exception as error:
            logger.exception("integration_job_failed", extra={"job": job.id})
            job.error = str(getattr(error, "detail", type(error).__name__))[
                :200
            ]
            job.next_attempt = utcnow() + timedelta(
                seconds=min(3600, 2**job.attempts * 10)
            )
            if job.attempts >= 5:
                job.status = "failed"


def deliver(db, job) -> None:
    """Deliver a queued message; ambiguous network failures may retry."""
    job.external_id = send_message(job.recipient, job.content)


def start_payment() -> None:
    """Initialize a durable payment with stable provider idempotency."""
    with SessionLocal.begin() as db:
        payment = db.scalar(
            select(Payment)
            .where(Payment.status == "initializing")
            .order_by(Payment.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not payment:
            return
        payment.provider_attempts += 1
        try:
            order = db.get(Order, payment.order_id)
            if order.status != "pending_payment":
                payment.status = "failed"
                return
            create_stripe_session(payment, order)
            payment.provider_error = ""
            customer = db.get(Customer, order.customer_id)
            queue_text(
                db,
                customer.phone,
                "Complete your payment: " + payment.checkout_url,
            )
        except HTTPException as error:
            payment.provider_error = str(error.detail)
            if payment.provider_attempts >= 5:
                payment.status = "failed"


def receive(db, job) -> None:
    """Process one already verified, deduplicated Meta message."""
    try:
        process_message(db, job.payload)
    except HTTPException as error:
        if error.status_code < 500:
            db.add(
                Notification(
                    recipient=job.payload["from"],
                    content={
                        "type": "text",
                        "text": {"body": str(error.detail)},
                    },
                )
            )
        else:
            raise


def expire_orders() -> None:
    """Release abandoned reservations in small locked batches."""
    with SessionLocal.begin() as db:
        orders = db.scalars(
            select(Order)
            .where(
                Order.status == "pending_payment", Order.expires_at < utcnow()
            )
            .with_for_update(skip_locked=True)
            .limit(10)
        )
        for order in orders:
            transition(db, order, "expired", "system")


async def worker_loop() -> None:
    """Poll at a conservative rate in a single background task."""
    while True:
        try:
            await asyncio.to_thread(process_one, WebhookJob, receive)
            await asyncio.to_thread(process_one, Notification, deliver)
            await asyncio.to_thread(expire_orders)
            await asyncio.to_thread(start_payment)
        except Exception:
            logger.exception("worker_iteration_failed")
        await asyncio.sleep(3)
