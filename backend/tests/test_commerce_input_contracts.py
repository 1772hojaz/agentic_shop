"""Focused regression coverage for backend contracts."""


def test_variant_price_precision():
    from decimal import Decimal

    import pytest
    from pydantic import ValidationError

    from app.schemas import VariantInput

    for price in ("-0.01", "1.001", "1000000000000", "NaN", "Infinity"):
        with pytest.raises(ValidationError):
            VariantInput(sku="SKU", price=price)
    assert VariantInput(sku="SKU", price="999999999999.99").price == Decimal(
        "999999999999.99"
    )


def test_opening_inventory_boundaries():
    import pytest
    from pydantic import ValidationError

    from app.schemas import VariantInput

    for field in ("quantity", "low_stock_threshold"):
        for value in (-1, 1000001):
            with pytest.raises(ValidationError):
                VariantInput(sku="SKU", price="0", **{field: value})
        for value in (0, 1000000):
            assert VariantInput(sku="SKU", price="0", **{field: value})


def test_product_variant_count():
    import pytest
    from pydantic import ValidationError

    from app.schemas import ProductInput

    variant = {"sku": "SKU", "price": "1.00"}
    for variants in ([], [variant] * 31):
        with pytest.raises(ValidationError):
            ProductInput(name="Shoes", variants=variants)
    assert (
        len(ProductInput(name="Shoes", variants=[variant] * 30).variants) == 30
    )


def test_product_image_schemes():
    import pytest
    from pydantic import ValidationError

    from app.schemas import ProductInput, ProductUpdate

    for model, extra in (
        (ProductInput, {"variants": [{"sku": "S", "price": 0}]}),
        (ProductUpdate, {}),
    ):
        for url in (
            "http://example.test/a.png",
            "javascript:alert(1)",
            "data:image/png;x",
        ):
            with pytest.raises(ValidationError):
                model(name="Product", image_url=url, **extra)
        for url in (
            "",
            "/uploads/image.png",
            "https://example.test/image.png",
        ):
            assert (
                model(name="Product", image_url=url, **extra).image_url == url
            )


def test_stock_adjustment_boundaries():
    import pytest
    from pydantic import ValidationError

    from app.schemas import StockInput

    for delta in (0, -1000001, 1000001):
        with pytest.raises(ValidationError):
            StockInput(variant_id="v", delta=delta, reason="Restock")
    for reason in ("  ", "ab", "x" * 201):
        with pytest.raises(ValidationError):
            StockInput(variant_id="v", delta=1, reason=reason)
    assert StockInput(variant_id="v", delta=-1000000, reason="Removal")


def test_cart_quantity_boundaries():
    import pytest
    from pydantic import ValidationError

    from app.schemas import CartInput

    for quantity in (-1, 1001):
        with pytest.raises(ValidationError):
            CartInput(variant_id="v", quantity=quantity)
    for quantity in (0, 1000):
        assert (
            CartInput(variant_id="v", quantity=quantity).quantity == quantity
        )


def test_checkout_contract():
    import pytest
    from pydantic import ValidationError

    from app.schemas import Checkout

    for key in ("x" * 15, "x" * 101):
        with pytest.raises(ValidationError):
            Checkout(checkout_key=key)
    with pytest.raises(ValidationError):
        Checkout(checkout_key="x" * 16, method="teleport")
    for method in ("collection", "delivery"):
        assert Checkout(checkout_key="x" * 100, method=method)


def test_staff_cannot_submit_payment_states():
    import pytest
    from pydantic import ValidationError

    from app.schemas import OrderStatus

    for status in (
        "paid",
        "refunded",
        "expired",
        "pending_payment",
        "unknown",
    ):
        with pytest.raises(ValidationError):
            OrderStatus(order_id="o", status=status)
    assert OrderStatus(order_id="o", status="processing")
