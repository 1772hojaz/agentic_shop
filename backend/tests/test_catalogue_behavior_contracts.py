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
