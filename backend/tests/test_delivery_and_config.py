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


