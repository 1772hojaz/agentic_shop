"""Verified Meta Cloud API ingress and expiring administrator pairing."""

import hashlib
import hmac
import secrets
from datetime import timedelta

import httpx
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.agent import chat
from app.auth import (
    CUSTOMER_PERMISSIONS,
    Principal,
    digest,
    user_principal,
)
from app.config import get_settings
from app.database import utcnow
from app.models import (
    AdminBinding,
    Conversation,
    Customer,
    Message,
    Notification,
    User,
    WebhookJob,
)
from app.registry import confirm_action
from app.schemas import ChatInput


def verify_meta(body: bytes, signature: str) -> None:
    """Verify raw webhook bytes with the Meta application secret."""
    secret = get_settings().meta_app_secret
    if not secret:
        raise HTTPException(503, "WhatsApp webhook is not configured")
    expected = (
        "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    )
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(401, "Invalid WhatsApp signature")


def ingest(db, payload: dict) -> dict:
    """Persist unique messages before acknowledging the Meta callback."""
    settings = get_settings()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            phone_id = value.get("metadata", {}).get("phone_number_id")
            if phone_id != settings.meta_phone_id:
                continue
            for status in value.get("statuses", []):
                db.execute(
                    update(Message)
                    .where(Message.external_id == status.get("id"))
                    .values(status=status.get("status", "unknown"))
                )
                db.execute(
                    update(Notification)
                    .where(Notification.external_id == status.get("id"))
                    .values(status=status.get("status", "unknown"))
                )
            for message in value.get("messages", []):
                try:
                    with db.begin_nested():
                        db.add(
                            WebhookJob(
                                external_id=message["id"], payload=message
                            )
                        )
                        db.flush()
                except IntegrityError:
                    continue
    return {"received": True}


def pairing_code(db, actor) -> dict:
    """Issue an expiring one-time code only after web authentication."""
    if actor.context != "admin":
        raise HTTPException(403, "Administrator authentication required")
    code = secrets.token_urlsafe(24)
    binding = AdminBinding(
        user_id=actor.id,
        code_hash=digest(code),
        expires_at=utcnow() + timedelta(minutes=5),
    )
    db.add(binding)
    return {"code": code, "instruction": "Send PAIR " + code + " to the shop"}


def pair_sender(db, phone: str, code: str) -> str:
    """Bind a verified Meta sender to a short-lived admin session."""
    binding = db.scalar(
        select(AdminBinding)
        .where(AdminBinding.code_hash == digest(code))
        .with_for_update()
    )
    if not binding or binding.used or binding.expires_at <= utcnow():
        return (
            "This pairing code is invalid or expired. Sign in and try again."
        )
    user = db.get(User, binding.user_id)
    if not user or not user.active:
        return "This administrator account is unavailable."
    binding.used = True
    binding.phone = phone
    binding.expires_at = utcnow() + timedelta(hours=1)
    return "Administrator access paired for one hour. Send UNPAIR to end it."


def sender_principal(db, phone: str) -> Principal:
    """Resolve admin authority from a paired session, never phone alone."""
    binding = db.scalar(
        select(AdminBinding)
        .where(
            AdminBinding.phone == phone,
            AdminBinding.used.is_(True),
            AdminBinding.expires_at > utcnow(),
        )
        .order_by(AdminBinding.created_at.desc())
    )
    if binding:
        user = db.get(User, binding.user_id)
        if user and user.active:
            return user_principal(db, user)
    customer = db.scalar(select(Customer).where(Customer.phone == phone))
    if not customer:
        customer = Customer(phone=phone)
        db.add(customer)
        db.flush()
    return Principal(customer.id, "customer", CUSTOMER_PERMISSIONS)


