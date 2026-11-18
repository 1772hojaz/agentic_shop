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


