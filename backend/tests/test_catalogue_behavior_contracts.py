"""Focused regression coverage for backend contracts."""


def test_archived_products_are_hidden(client, product, store):
    from app.models import Product

    with store.begin() as db:
        db.get(Product, product["id"]).active = False
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


def test_catalogue_search_case_insensitivity(client, product):
    for query in ("RUNNING", "running", "RuNnInG"):
        response = client.get("/api/v1/products", params={"query": query})
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [
            product["id"]
        ]


def test_catalogue_percent_is_literal(client, product, store):
    from app.models import Product

    assert (
        client.get("/api/v1/products", params={"query": "%"}).json()["total"]
        == 0
    )
    with store.begin() as db:
        db.get(Product, product["id"]).name = "100% cotton"
    assert (
        client.get("/api/v1/products", params={"query": "%"}).json()["total"]
        == 1
    )


def test_catalogue_price_ceiling(client, product):
    assert (
        client.get("/api/v1/products", params={"max_price": "25.49"}).json()[
            "total"
        ]
        == 0
    )
    response = client.get("/api/v1/products", params={"max_price": "25.50"})
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == product["id"]


def test_catalogue_offset_preserves_total(client, product):
    response = client.get("/api/v1/products", params={"offset": 1, "limit": 1})
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 1}


def test_cart_quantity_replaces_existing_line(client, headers, product):
    variant = product["variants"][0]["id"]
    for quantity in (2, 3):
        response = client.put(
            "/api/v1/carts/me/items",
            headers=headers["customer1"],
            json={"variant_id": variant, "quantity": quantity},
        )
        assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["quantity"] == 3
    assert float(response.json()["total"]) == 76.5


def test_archived_cart_item_can_be_removed(client, headers, product, store):
    from app.models import Product

    payload = {"variant_id": product["variants"][0]["id"], "quantity": 1}
    assert (
        client.put(
            "/api/v1/carts/me/items",
            headers=headers["customer1"],
            json=payload,
        ).status_code
        == 200
    )
    with store.begin() as db:
        db.get(Product, product["id"]).active = False
    payload["quantity"] = 0
    response = client.put(
        "/api/v1/carts/me/items", headers=headers["customer1"], json=payload
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert float(response.json()["total"]) == 0


def test_unavailable_cart_change_keeps_previous_quantity(
    client, headers, product
):
    payload = {"variant_id": product["variants"][0]["id"], "quantity": 2}
    assert (
        client.put(
            "/api/v1/carts/me/items",
            headers=headers["customer1"],
            json=payload,
        ).status_code
        == 200
    )
    payload["quantity"] = 11
    assert (
        client.put(
            "/api/v1/carts/me/items",
            headers=headers["customer1"],
            json=payload,
        ).status_code
        == 409
    )
    cart = client.get("/api/v1/carts/me", headers=headers["customer1"]).json()
    assert len(cart["items"]) == 1
    assert cart["items"][0]["quantity"] == 2


def test_empty_cart_cannot_create_order(client, headers, store):
    from sqlalchemy import func, select

    from app.models import Order

    response = client.post(
        "/api/v1/orders",
        headers=headers["customer1"],
        json={"checkout_key": "empty-cart-checkout-0001"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Cart is empty"
    with store() as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 0


def test_delivery_requires_address_and_preserves_cart(
    client, headers, product, store
):
    from app.models import Inventory

    variant = product["variants"][0]["id"]
    assert (
        client.put(
            "/api/v1/carts/me/items",
            headers=headers["customer1"],
            json={"variant_id": variant, "quantity": 2},
        ).status_code
        == 200
    )
    response = client.post(
        "/api/v1/orders",
        headers=headers["customer1"],
        json={
            "checkout_key": "delivery-no-address-0001",
            "method": "delivery",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Delivery address required"
    cart = client.get("/api/v1/carts/me", headers=headers["customer1"]).json()
    assert cart["items"][0]["quantity"] == 2
    with store() as db:
        assert db.get(Inventory, variant).quantity == 10
