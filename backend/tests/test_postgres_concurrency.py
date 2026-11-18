"""Production row-lock coverage on a disposable test database."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException

from app.auth import CUSTOMER_PERMISSIONS, Principal
from app.catalogue import set_cart
from app.models import Inventory
from app.orders import checkout
from app.schemas import CartInput, Checkout


def test_concurrent_checkout_never_oversells(store, identities, product):
    with store() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("Requires disposable PostgreSQL TEST_DATABASE_URL")
    variant = product["variants"][0]["id"]
    actors = [
        Principal(identities[name]["id"], "customer", CUSTOMER_PERMISSIONS)
        for name in ("customer1", "customer2")
    ]
    for actor in actors:
        with store.begin() as db:
            set_cart(db, actor, CartInput(variant_id=variant, quantity=8))
    barrier = Barrier(2)

    def buy(actor):
        barrier.wait(timeout=10)
        try:
            with store.begin() as db:
                checkout(
                    db, actor, Checkout(checkout_key="concurrent-" + actor.id)
                )
            return 201
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(buy, actors)) == [201, 409]
    with store() as db:
        assert db.get(Inventory, variant).quantity == 2
