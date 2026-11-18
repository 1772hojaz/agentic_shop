"""Signed ingress, replay protection, pairing and agent tool boundaries."""

import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.auth import CUSTOMER_PERMISSIONS, Principal, user_principal
from app.config import get_settings
from app.models import Inventory, Order, Payment, User, WebhookJob
from app.registry import execute_tool, model_tools
from app.whatsapp import pair_sender, pairing_code, sender_principal
from tests.test_commerce import place_order


@pytest.fixture
def integration_config(monkeypatch):
    config = get_settings()
    monkeypatch.setattr(config, "meta_app_secret", "test-meta-secret")
    monkeypatch.setattr(config, "meta_verify_token", "test-verify")
    monkeypatch.setattr(config, "meta_phone_id", "12345")
    monkeypatch.setattr(config, "stripe_webhook_secret", "test-stripe-secret")
    return config


def test_meta_verification_and_invalid_signature(client, integration_config):
    result = client.get(
        "/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=test-verify&hub.challenge=42"
    )
    assert result.status_code == 200
    assert result.text == "42"
    assert client.post("/webhooks/whatsapp", json={}).status_code == 401


def test_meta_inbox_deduplicates(client, integration_config, store):
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "12345"},
                            "messages": [
                                {
                                    "id": "wamid-1",
                                    "from": "250700000001",
                                    "type": "text",
                                    "text": {"body": "Hello"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    body = json.dumps(payload).encode()
    signature = (
        "sha256="
        + hmac.new(b"test-meta-secret", body, hashlib.sha256).hexdigest()
    )
    for _ in range(2):
        response = client.post(
            "/webhooks/whatsapp",
            content=body,
            headers={"X-Hub-Signature-256": signature},
        )
        assert response.status_code == 200, response.text
    with store() as db:
        assert db.query(WebhookJob).count() == 1


def signed_payment(client, payload):
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"test-stripe-secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return client.post(
        "/webhooks/payments",
        content=body,
        headers={
            "Stripe-Signature": f"t={timestamp},v1={signature}",
        },
    )


def test_payment_amount_check_replay_and_separate_state(
    client, headers, product, store, integration_config
):
    order = place_order(client, headers, product)
    with store.begin() as db:
        payment = Payment(
            order_id=order["id"],
            method="stripe",
            amount=Decimal("51.00"),
            currency="USD",
            reference="cs_test_1",
        )
        db.add(payment)
        db.flush()
        payment_id = payment.id
    event = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_1",
                "metadata": {"payment_id": payment_id},
                "payment_status": "paid",
                "amount_total": 1,
                "currency": "usd",
            }
        },
    }
    assert signed_payment(client, event).status_code == 422
    with store() as db:
        assert db.get(Order, order["id"]).status == "pending_payment"
    event["data"]["object"]["amount_total"] = 5100
    assert signed_payment(client, event).status_code == 200
    assert signed_payment(client, event).json()["duplicate"]
    with store() as db:
        assert db.get(Order, order["id"]).status == "paid"
        assert db.get(Inventory, product["variants"][0]["id"]).quantity == 8


def test_invalid_payment_signature(client, integration_config):
    assert (
        client.post(
            "/webhooks/payments",
            json={},
            headers={
                "Stripe-Signature": "t=1,v1=wrong",
            },
        ).status_code
        == 401
    )


def test_admin_phone_requires_pairing_and_single_use_code(store, identities):
    phone = "250700000099"
    with store.begin() as db:
        user = db.get(User, identities["owner"]["id"])
        actor = user_principal(db, user)
        assert sender_principal(db, phone).context == "customer"
        code = pairing_code(db, actor)["code"]
        db.flush()
        assert "paired" in pair_sender(db, phone, code)
        assert sender_principal(db, phone).context == "admin"
        assert "invalid" in pair_sender(db, phone, code)


def test_model_cannot_confirm_or_escalate(store, identities, product):
    actor = Principal(
        identities["customer1"]["id"], "customer", CUSTOMER_PERMISSIONS
    )
    names = {tool["function"]["name"] for tool in model_tools(actor)}
    assert "stock_adjustment" not in names
    assert not any("confirm" in name for name in names)
    with store.begin() as db:
        with pytest.raises(HTTPException) as denied:
            execute_tool(
                db,
                actor,
                "stock_adjustment",
                {
                    "variant_id": product["variants"][0]["id"],
                    "delta": 100,
                    "reason": "Ignore all permissions",
                },
            )
        assert denied.value.status_code == 403


def test_agent_uses_real_tools_and_records_usage(
    client, headers, product, monkeypatch
):
    from app import agent

    config = get_settings()
    monkeypatch.setattr(config, "ai_api_key", "test-provider-key")
    monkeypatch.setattr(config, "ai_model", "test-model")
    responses = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "product_search",
                                        "arguments": '{"query":"running"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Running shoes cost 25.50.",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 150, "completion_tokens": 15},
            },
        ]
    )
    captured = []

    def request(history, tools, model):
        captured.append(list(history))
        return next(responses)

    monkeypatch.setattr(agent, "model_request", request)
    result = client.post(
        "/api/v1/ai/chat",
        headers=headers["customer1"],
        json={"message": "Find running shoes"},
    )
    assert result.status_code == 200, result.text
    assert "25.50" in result.json()["message"]
    assert any(
        message["role"] == "tool" and "Running shoes" in message["content"]
        for message in captured[1]
    )
    usage = client.get("/api/v1/ai/usage", headers=headers["owner"]).json()
    assert usage["input_tokens"] == 250


def test_unconfigured_agent_is_explicit(client, headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_api_key", "")
    assert (
        client.post(
            "/api/v1/ai/chat",
            headers=headers["owner"],
            json={"message": "Hello"},
        ).status_code
        == 503
    )
