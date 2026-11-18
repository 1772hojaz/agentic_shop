"""Durable provider work, configured controls and cash fulfillment."""

from decimal import Decimal

from app.models import Order, Payment
from app.orders import transition
from app.payments import payment_event, settle_payment
from tests.test_commerce import place_order


def test_cash_delivery_remains_unpaid_until_receipt(
    client, headers, product, store
):
    order = place_order(client, headers, product)
    payment = client.post(
        "/api/v1/payments/initiate",
        headers=headers["customer1"],
        json={"order_id": order["id"], "method": "cash"},
    ).json()
    with store.begin() as db:
        record = db.get(Order, order["id"])
        transition(db, record, "processing", "staff")
        transition(db, record, "ready_for_delivery", "staff")
        assert db.get(Payment, payment["id"]).status == "pending"
        settle_payment(db, db.get(Payment, payment["id"]), "staff")
        transition(db, record, "completed", "staff")
    with store() as db:
        assert db.get(Order, order["id"]).status == "completed"


def test_durable_stripe_initialization_uses_stable_payment_id(
    client, headers, product, store, monkeypatch
):
    from app import payments, worker
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "stripe_secret_key", "test-key")
    order = place_order(client, headers, product)
    payment = client.post(
        "/api/v1/payments/initiate",
        headers=headers["customer1"],
        json={"order_id": order["id"], "method": "stripe"},
    ).json()
    assert payment["status"] == "initializing"
    observed = []

    def provider(path, payload, key):
        observed.append(key)
        return {
            "id": "cs_real_contract",
            "url": "https://checkout.stripe.com/test",
        }

    monkeypatch.setattr(payments, "stripe_request", provider)
    monkeypatch.setattr(worker, "SessionLocal", store)
    worker.start_payment()
    worker.start_payment()
    assert observed == [payment["id"]]
    with store() as db:
        assert db.get(Payment, payment["id"]).status == "pending"
        assert db.get(Order, order["id"]).status == "pending_payment"


def test_agent_configuration_requires_confirmation(client, headers):
    config = client.get("/api/v1/ai/config", headers=headers["owner"]).json()
    config["model"] = "operator-selected-model"
    pending = client.put(
        "/api/v1/ai/config",
        headers=headers["owner"],
        json=config,
    ).json()
    assert pending["confirmation_required"]
    assert (
        client.get("/api/v1/ai/config", headers=headers["owner"]).json()[
            "model"
        ]
        != config["model"]
    )
    assert (
        client.post(
            f"/api/v1/confirmations/{pending['id']}/confirm",
            headers=headers["owner"],
        ).status_code
        == 200
    )
    assert (
        client.get("/api/v1/ai/config", headers=headers["owner"]).json()[
            "model"
        ]
        == config["model"]
    )


def test_refund_webhook_replay_cannot_resurrect_paid_state(
    client, headers, product, store
):
    order = place_order(client, headers, product)
    with store.begin() as db:
        payment = Payment(
            order_id=order["id"],
            amount=Decimal("51.00"),
            currency="USD",
            method="stripe",
            reference="cs_refund",
            status="paid",
        )
        db.add(payment)
        record = db.get(Order, order["id"])
        record.status = "refund_pending"
        db.flush()
        payload = {
            "id": "evt_refund",
            "type": "refund.updated",
            "data": {
                "object": {
                    "metadata": {"payment_id": payment.id},
                    "amount": 5100,
                    "currency": "usd",
                    "status": "succeeded",
                },
            },
        }
        payment_event(db, payload)
        assert payment.status == "refunded"
        assert record.status == "refunded"
        settle_payment(db, payment, "stripe")
        assert payment.status == "refunded"


def test_image_upload_rejects_non_images(client, headers):
    response = client.post(
        "/api/v1/uploads",
        headers=headers["owner"],
        files={"file": ("attack.jpg", b"<script>bad</script>", "image/jpeg")},
    )
    assert response.status_code == 422
