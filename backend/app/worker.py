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


