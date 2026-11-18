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


def process_message(db, payload: dict) -> None:
    """Handle explicit human commands before entering the model loop."""
    phone = payload["from"]
    text = incoming_text(payload)
    if text.startswith("PAIR "):
        answer = pair_sender(db, phone, text[5:].strip())
    elif text == "UNPAIR":
        db.execute(
            update(AdminBinding)
            .where(AdminBinding.phone == phone)
            .values(expires_at=utcnow())
        )
        answer = "Administrator session ended."
    else:
        actor = sender_principal(db, phone)
        answer = respond(db, actor, text)
    db.add(
        Notification(
            recipient=phone,
            content={"type": "text", "text": {"body": answer}},
        )
    )


def incoming_text(payload: dict) -> str:
    """Interpret text, interactive replies and attachment metadata safely."""
    kind = payload.get("type")
    if kind == "text":
        return payload.get("text", {}).get("body", "")[:4000]
    if kind == "interactive":
        reply = payload.get("interactive", {})
        selection = reply.get("button_reply", reply.get("list_reply", {}))
        return selection.get("id", "")[:4000]
    if kind in {"image", "document"}:
        attachment = payload.get(kind, {})
        caption = attachment.get("caption", "")
        return (
            f"Customer sent a {kind} attachment. Caption: {caption[:1500]}. "
            "The attachment contents have not been inspected. Ask for a "
            "text description when needed; do not infer its contents."
        )
    return "Please explain which message types this shopping service supports."


def respond(db, actor, text: str) -> str:
    """Keep human confirmations outside the set of model-callable tools."""
    if text.startswith("CONFIRM "):
        confirm_action(db, actor, text[8:].strip())
        return "The confirmed operation completed successfully."
    conversation = db.scalar(
        select(Conversation)
        .where(
            Conversation.principal_id == actor.id,
            Conversation.channel == "whatsapp",
            Conversation.context == actor.context,
        )
        .order_by(Conversation.created_at.desc())
    )
    try:
        result = chat(
            db,
            actor,
            ChatInput(
                message=text or "Hello",
                conversation_id=conversation.id if conversation else None,
            ),
            "whatsapp",
        )
    except HTTPException as error:
        if error.status_code in {429, 502, 503}:
            return str(error.detail) + ". Please try again later."
        raise
    answer = result["message"]
    for item in result["confirmations"]:
        answer += f"\nTo approve {item['action']}, send CONFIRM {item['id']}"
    return answer[:4000]


def send_message(recipient: str, content: dict) -> str:
    """Deliver a real message using the official Meta Cloud API."""
    settings = get_settings()
    required = (
        settings.meta_access_token,
        settings.meta_phone_id,
        settings.meta_graph_version,
    )
    if not all(required):
        raise HTTPException(503, "WhatsApp delivery is not configured")
    url = (
        "https://graph.facebook.com/"
        + settings.meta_graph_version
        + "/"
        + settings.meta_phone_id
        + "/messages"
    )
    try:
        response = httpx.post(
            url,
            headers={
                "Authorization": "Bearer " + (settings.meta_access_token)
            },
            json={"messaging_product": "whatsapp", "to": recipient, **content},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()["messages"][0]["id"]
    except (httpx.HTTPError, KeyError) as error:
        raise HTTPException(502, "WhatsApp delivery failed") from error
