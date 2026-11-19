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
