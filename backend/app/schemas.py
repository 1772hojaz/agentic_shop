"""Strict request contracts shared by REST routes and agent tools."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    """Reject unrecognized arguments at every business boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(StrictModel):
    """Credentials submitted over HTTPS."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class StaffInput(StrictModel):
    """Owner-controlled staff registration."""

    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["owner", "manager", "staff"] = "staff"


class StaffUpdate(StrictModel):
    """Changes to an existing staff account."""

    role: Literal["owner", "manager", "staff"]
    active: bool = True


class CategoryInput(StrictModel):
    """A unique readable category name."""

    name: str = Field(min_length=1, max_length=100)


class VariantInput(StrictModel):
    """Priced product option with an opening stock balance."""

    sku: str = Field(min_length=1, max_length=100)
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    options: dict[str, str] = Field(default_factory=dict, max_length=10)
    quantity: int = Field(default=0, ge=0, le=1000000)
    low_stock_threshold: int = Field(default=5, ge=0, le=1000000)


class ProductInput(StrictModel):
    """Catalogue product and one or more sellable variants."""

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)
    category_id: str | None = None
    image_url: str = Field(default="", max_length=500)
    active: bool = True
    variants: list[VariantInput] = Field(min_length=1, max_length=30)

    @field_validator("image_url")
    @classmethod
    def safe_image(cls, value):
        """Accept local uploads and HTTPS images only."""
        if value and not value.startswith(("/uploads/", "https://")):
            raise ValueError("Use an HTTPS image or an uploaded file")
        return value


class ProductUpdate(StrictModel):
    """Editable catalogue fields; price changes use confirmation."""

    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=5000)
    category_id: str | None = None
    active: bool = True
    image_url: str = ""

    _safe_image = field_validator("image_url")(ProductInput.safe_image)


class ProductChange(ProductUpdate):
    """Tool-scoped product identifier and strictly editable fields."""

    product_id: str


class Search(StrictModel):
    """Public product discovery criteria."""

    query: str = Field(default="", max_length=160)
    max_price: Decimal | None = Field(default=None, ge=0)
    category_id: str | None = None


class StockInput(StrictModel):
    """Relative stock adjustment; zero is not an adjustment."""

    variant_id: str
    delta: int = Field(ge=-1000000, le=1000000)
    reason: str = Field(min_length=3, max_length=200)

    @field_validator("delta")
    @classmethod
    def nonzero_delta(cls, value):
        """Reject adjustments that do not move stock."""
        if not value:
            raise ValueError("Stock adjustment must be nonzero")
        return value


