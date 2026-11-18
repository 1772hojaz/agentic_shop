"""Regression coverage for authentication, ownership and confirmations."""

from datetime import timedelta

from app.auth import digest
from app.database import utcnow
from app.models import AuthSession, Confirmation, Inventory, User


def test_login_cookie_csrf_and_logout(client, identities):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "owner@example.test",
            "password": "correct-password-123",
        },
    )
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "password_hash" not in response.json()["user"]
    csrf = response.json()["csrf_token"]
    assert (
        client.post("/api/v1/categories", json={"name": "Blocked"}).status_code
        == 403
    )
    forged = client.post(
        "/api/v1/categories",
        json={"name": "Blocked"},
        headers={"Authorization": "nonsense"},
    )
    assert forged.status_code == 403
    assert (
        client.post(
            "/api/v1/categories",
            json={"name": "Shoes"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_login_rate_limit_persists(client, identities):
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.test",
                "password": "wrong",
            },
        )
        assert response.status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "owner@example.test",
                "password": "correct-password-123",
            },
        ).status_code
        == 429
    )


def test_permissions_and_unknown_parameters(client, headers, product):
    variant = product["variants"][0]["id"]
    assert (
        client.post(
            "/api/v1/staff",
            headers=headers["manager"],
            json={
                "email": "bad@example.test",
                "name": "No",
                "password": "long-password",
            },
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/inventory/{variant}",
            headers=headers["customer1"],
            json={
                "variant_id": variant,
                "delta": 5,
                "reason": "Override",
            },
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/carts/me/items",
            headers=headers["customer1"],
            json={
                "variant_id": variant,
                "quantity": 1,
                "customer_id": "another",
            },
        ).status_code
        == 422
    )


def test_exact_single_use_actor_confirmation(client, headers, product, store):
    variant = product["variants"][0]["id"]
    response = client.patch(
        f"/api/v1/inventory/{variant}",
        headers=headers["owner"],
        json={
            "variant_id": variant,
            "delta": 5,
            "reason": "Restock",
        },
    )
    pending = response.json()
    assert pending["confirmation_required"]
    with store() as db:
        assert db.get(Inventory, variant).quantity == 10
    path = f"/api/v1/confirmations/{pending['id']}/confirm"
    assert client.post(path, headers=headers["manager"]).status_code == 404
    assert client.post(path, headers=headers["owner"]).status_code == 200
    assert client.post(path, headers=headers["owner"]).status_code == 409
    with store() as db:
        assert db.get(Inventory, variant).quantity == 15


def test_expired_confirmation_and_session(
    client, headers, product, store, identities
):
    variant = product["variants"][0]["id"]
    pending = client.patch(
        f"/api/v1/inventory/{variant}",
        headers=headers["owner"],
        json={
            "variant_id": variant,
            "delta": 5,
            "reason": "Restock",
        },
    ).json()
    with store.begin() as db:
        db.get(Confirmation, pending["id"]).expires_at = utcnow() - timedelta(
            seconds=1
        )
    assert (
        client.post(
            f"/api/v1/confirmations/{pending['id']}/confirm",
            headers=headers["owner"],
        ).status_code
        == 409
    )
    with store.begin() as db:
        db.get(
            AuthSession, digest(identities["owner"]["token"])
        ).expires_at = utcnow() - timedelta(seconds=1)
    assert (
        client.get("/api/v1/auth/me", headers=headers["owner"]).status_code
        == 401
    )


def test_disabled_users_and_owner_self_protection(
    client, headers, store, identities
):
    owner = identities["owner"]["id"]
    assert (
        client.patch(
            f"/api/v1/staff/{owner}",
            headers=headers["owner"],
            json={
                "role": "staff",
                "active": False,
            },
        ).status_code
        == 409
    )
    with store.begin() as db:
        db.get(User, identities["manager"]["id"]).active = False
    assert (
        client.get("/api/v1/orders", headers=headers["manager"]).status_code
        == 401
    )


def test_password_validation_never_echoes_secrets(client, headers):
    secret = "short"
    result = client.post(
        "/api/v1/staff",
        headers=headers["owner"],
        json={
            "email": "x@example.test",
            "name": "X",
            "password": secret,
        },
    )
    assert result.status_code == 422
    assert secret not in result.text


def test_unauthenticated_private_routes(client):
    for path in (
        "/api/v1/orders",
        "/api/v1/customers",
        "/api/v1/ai/usage",
        "/api/v1/settings",
        "/api/v1/staff",
        "/api/v1/audit",
    ):
        assert client.get(path).status_code == 401
