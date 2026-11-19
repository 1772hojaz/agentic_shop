"""Focused regression coverage for backend contracts."""


def test_archived_products_are_hidden(client, product, store):
    from app.models import Product

    with store.begin() as db:
        db.get(Product, product["id"]).active = False
    response = client.get("/api/v1/products")
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0
