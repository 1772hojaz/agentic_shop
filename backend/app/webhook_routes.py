"""Public integration endpoints with provider authentication."""

import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.config import get_settings
from app.database import get_db
from app.payments import payment_event, verify_stripe_signature
from app.whatsapp import ingest, verify_meta

router = APIRouter(tags=["Verified webhooks"])


@router.get("/webhooks/whatsapp", response_class=PlainTextResponse)
def verify_whatsapp(request: Request):
    """Answer the Meta subscription challenge with a constant-time check."""
    token = get_settings().meta_verify_token
    supplied = request.query_params.get("hub.verify_token", "")
    mode = request.query_params.get("hub.mode")
    if (
        not token
        or mode != "subscribe"
        or not hmac.compare_digest(supplied, token)
    ):
        raise HTTPException(403, "Invalid verification token")
    return request.query_params.get("hub.challenge", "")


@router.post("/webhooks/whatsapp")
async def whatsapp(request: Request, db=Depends(get_db)):
    """Authenticate before parsing, then acknowledge durable receipt."""
    body = await request.body()
    verify_meta(body, request.headers.get("x-hub-signature-256", ""))
    try:
        payload = json.loads(body)
        return ingest(db, payload)
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(422, "Invalid WhatsApp event") from error


@router.post("/webhooks/payments")
async def payments(request: Request, db=Depends(get_db)):
    """Apply only verified, replay-protected payment callbacks."""
    body = await request.body()
    event = verify_stripe_signature(
        body, request.headers.get("stripe-signature", "")
    )
    try:
        return payment_event(db, event)
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(422, "Invalid payment event") from error
