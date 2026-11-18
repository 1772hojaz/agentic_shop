"""Order/payment separation, stock integrity and customer isolation."""

from decimal import Decimal

from app.models import Inventory, Order, OrderItem, Variant


def place_order(
    client, headers, product, key="checkout-request-0001", quantity=2
):
    variant = product["variants"][0]["id"]
    response = client.put(
        "/api/v1/carts/me/items",
        headers=headers["customer1"],
        json={"variant_id": variant, "quantity": quantity},
    )
    assert response.status_code == 200, response.text
    result = client.post(
        "/api/v1/orders",
        headers=headers["customer1"],
        json={
            "checkout_key": key,
            "method": "collection",
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def test_checkout_idempotency_and_snapshots(client, headers, product, store):
    order = place_order(client, headers, product)
    assert order["status"] == "pending_payment"
    assert Decimal(str(order["total"])) == Decimal("51.00")
    repeated = client.post(
        "/api/v1/orders",
        headers=headers["customer1"],
        json={
            "checkout_key": "checkout-request-0001",
            "method": "collection",
        },
    )
    assert repeated.json()["id"] == order["id"]
    with store.begin() as db:
        variant = db.get(Variant, product["variants"][0]["id"])
        variant.price = Decimal("99.99")
        assert db.get(Inventory, variant.id).quantity == 8
    detail = client.get(
        f"/api/v1/orders/{order['id']}", headers=headers["customer1"]
    ).json()
    assert Decimal(str(detail["items"][0]["unit_price"])) == Decimal("25.50")


def test_customer_order_and_cart_isolation(client, headers, product):
    order = place_order(client, headers, product)
    assert (
        client.get(
            f"/api/v1/orders/{order['id']}", headers=headers["customer2"]
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/orders", headers=headers["customer2"]).json()[
            "total"
        ]
        == 0
    )
    assert (
        client.get("/api/v1/carts/me", headers=headers["customer2"]).json()[
            "items"
        ]
        == []
    )
    assert (
        client.post(
            "/api/v1/payments/initiate",
            headers=headers["customer2"],
            json={
                "order_id": order["id"],
                "method": "cash",
            },
        ).status_code
        == 404
    )


def test_stale_cart_cannot_oversell(client, headers, product, store):
    variant = product["variants"][0]["id"]
    assert (
        client.put(
            "/api/v1/carts/me/items",
            headers=headers["customer1"],
            json={
                "variant_id": variant,
                "quantity": 8,
            },
        ).status_code
        == 200
    )
    with store.begin() as db:
        db.get(Inventory, variant).quantity = 1
    result = client.post(
        "/api/v1/orders",
        headers=headers["customer1"],
        json={
            "checkout_key": "checkout-stale-000001",
            "method": "collection",
        },
    )
    assert result.status_code == 409
    with store() as db:
        assert db.query(Order).count() == 0
        assert db.query(OrderItem).count() == 0
        assert db.get(Inventory, variant).quantity == 1


def test_cash_initiation_does_not_pay_and_settlement_is_confirmed(
    client, headers, product
):
    order = place_order(client, headers, product)
    payment = client.post(
        "/api/v1/payments/initiate",
        headers=headers["customer1"],
        json={
            "order_id": order["id"],
            "method": "cash",
        },
    ).json()
    assert payment["status"] == "pending"
    detail = client.get(
        f"/api/v1/orders/{order['id']}", headers=headers["owner"]
    ).json()
    assert detail["status"] == "pending_payment"
    pending = client.post(
        f"/api/v1/payments/{payment['id']}/settle-cash",
        headers=headers["owner"],
    ).json()
    assert pending["confirmation_required"]
    assert (
        client.post(
            f"/api/v1/confirmations/{pending['id']}/confirm",
            headers=headers["owner"],
        ).status_code
        == 200
    )
    detail = client.get(
        f"/api/v1/orders/{order['id']}", headers=headers["owner"]
    ).json()
    assert detail["status"] == "paid"
    assert detail["payments"][0]["status"] == "paid"


def test_cancel_releases_stock_once_and_invalid_transition_rolls_back(
    client, headers, product, store
):
    order = place_order(client, headers, product)
    data = {"order_id": order["id"], "status": "completed"}
    pending = client.patch(
        f"/api/v1/orders/{order['id']}/status",
        headers=headers["owner"],
        json=data,
    ).json()
    path = f"/api/v1/confirmations/{pending['id']}/confirm"
    assert client.post(path, headers=headers["owner"]).status_code == 409
    data["status"] = "cancelled"
    pending = client.patch(
        f"/api/v1/orders/{order['id']}/status",
        headers=headers["owner"],
        json=data,
    ).json()
    path = f"/api/v1/confirmations/{pending['id']}/confirm"
    assert client.post(path, headers=headers["owner"]).status_code == 200
    assert client.post(path, headers=headers["owner"]).status_code == 409
    with store() as db:
        assert db.get(Inventory, product["variants"][0]["id"]).quantity == 10


def test_stripe_unconfigured_fails_closed(
    client, headers, product, monkeypatch
):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "stripe_secret_key", "")
    order = place_order(client, headers, product)
    response = client.post(
        "/api/v1/payments/initiate",
        headers=headers["customer1"],
        json={
            "order_id": order["id"],
            "method": "stripe",
        },
    )
    assert response.status_code == 503


def test_pagination_validation_and_public_catalogue(client, headers, product):
    assert client.get("/api/v1/products?limit=1000").status_code == 422
    assert client.get("/api/v1/products?max_price=20").json()["total"] == 0
    assert client.get("/api/v1/products?query=running").json()["total"] == 1


def test_reports_exclude_pending_revenue(client, headers, product):
    place_order(client, headers, product)
    report = client.get(
        "/api/v1/reports/sales", headers=headers["owner"]
    ).json()
    assert Decimal(str(report["revenue"])) == 0
    assert report["total_orders"] == 1


def test_multi_item_checkout_failure_rolls_back_all_reservations(
    client, headers, product, store
):
    first = product["variants"][0]["id"]
    second = client.post(
        f"/api/v1/products/{product['id']}/variants",
        headers=headers["owner"],
        json={"sku": "RUN-43", "price": "30.00", "quantity": 5},
    ).json()["id"]
    for variant in (first, second):
        assert (
            client.put(
                "/api/v1/carts/me/items",
                headers=headers["customer1"],
                json={"variant_id": variant, "quantity": 2},
            ).status_code
            == 200
        )
    with store.begin() as db:
        db.get(Inventory, max(first, second)).quantity = 0
        before = {
            key: db.get(Inventory, key).quantity for key in (first, second)
        }
    result = client.post(
        "/api/v1/orders",
        headers=headers["customer1"],
        json={"checkout_key": "multi-line-rollback-0001"},
    )
    assert result.status_code == 409
    with store() as db:
        assert db.query(Order).count() == 0
        assert {
            key: db.get(Inventory, key).quantity for key in (first, second)
        } == before
