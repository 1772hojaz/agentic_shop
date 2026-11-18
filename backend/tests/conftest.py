"""Isolated SQLite fixtures; never connect tests to the configured shop."""

import os
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.auth import (
    assign_role,
    create_session,
    digest,
    hash_password,
    seed_roles,
)
from app.database import Base, get_db, make_engine, utcnow
from app.main import app, limits
from app.models import AuthSession, Customer, User


@pytest.fixture
def store(tmp_path):
    url = os.environ.get("TEST_DATABASE_URL", "")
    if url and not url.split("/")[-1].endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must name a disposable _test DB")
    engine = make_engine(url or "sqlite:///" + str(tmp_path / "test.db"))
    if url:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    if url:
        Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(store):
    def database():
        with store.begin() as session:
            yield session

    app.dependency_overrides[get_db] = database
    limits.clear()
    client = TestClient(app)
    yield client
    client.close()
    app.dependency_overrides.clear()


@pytest.fixture
def identities(store):
    records = {}
    with store.begin() as db:
        seed_roles(db)
        for role in ("owner", "manager", "staff"):
            user = User(
                email=role + "@example.test",
                name=role,
                password_hash=hash_password("correct-password-123"),
            )
            db.add(user)
            db.flush()
            assign_role(db, user.id, role)
            db.flush()
            token, _ = create_session(db, user.id)
            records[role] = {"id": user.id, "token": token}
        for index in (1, 2):
            customer = Customer(phone=f"25070000000{index}")
            db.add(customer)
            db.flush()
            token = f"customer-test-token-{index}"
            db.add(
                AuthSession(
                    token_hash=digest(token),
                    customer_id=customer.id,
                    csrf="test",
                    expires_at=utcnow() + timedelta(hours=1),
                )
            )
            records[f"customer{index}"] = {"id": customer.id, "token": token}
    return records


@pytest.fixture
def headers(identities):
    return {
        name: {"Authorization": "Bearer " + item["token"]}
        for name, item in identities.items()
    }


@pytest.fixture
def product(client, headers):
    response = client.post(
        "/api/v1/products",
        headers=headers["owner"],
        json={
            "name": "Running shoes",
            "description": "Black running shoes",
            "variants": [
                {
                    "sku": "RUN-42",
                    "price": "25.50",
                    "quantity": 10,
                    "options": {"size": "42", "colour": "black"},
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()
