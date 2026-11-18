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


class PriceInput(StrictModel):
    """Exact price change requiring actor confirmation."""

    variant_id: str
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)


class ThresholdInput(StrictModel):
    """Confirmed change to a variant's low-stock alert threshold."""

    variant_id: str
    threshold: int = Field(ge=0, le=1000000)


class CartInput(StrictModel):
    """Set a cart quantity, or remove an item using zero."""

    variant_id: str
    quantity: int = Field(ge=0, le=1000)


class Checkout(StrictModel):
    """Customer-supplied fulfillment choice and idempotency key."""

    checkout_key: str = Field(min_length=16, max_length=100)
    method: Literal["collection", "delivery"] = "collection"
    address: str = Field(default="", max_length=500)


class OrderStatus(StrictModel):
    """Explicit requested transition with optional delivery details."""

    order_id: str
    status: Literal[
        "processing",
        "ready_for_delivery",
        "out_for_delivery",
        "delivered",
        "completed",
        "cancelled",
        "delivery_failed",
        "refund_pending",
    ]
    tracking: str = Field(default="", max_length=200)


class PaymentInput(StrictModel):
    """Supported initial payment methods."""

    order_id: str
    method: Literal["stripe", "cash"]


class NotificationInput(StrictModel):
    """A structured WhatsApp message sent by authorised staff."""

    customer_id: str
    text: str = Field(min_length=1, max_length=4000)
    kind: Literal["text", "image", "document", "interactive", "template"] = (
        "text"
    )
    media_url: str = Field(default="", max_length=500)
    template_name: str = Field(default="", max_length=100)
    language: str = Field(default="en_US", max_length=10)


class ChatInput(StrictModel):
    """A message scoped to a verified principal's conversation."""

    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None


class SettingInput(StrictModel):
    """Non-secret shop configuration controlled by the owner."""

    name: str = Field(default="Agentic Shop", max_length=100)
    contact: str = Field(default="", max_length=100)
    delivery_instructions: str = Field(default="", max_length=1000)
    support_message: str = Field(default="", max_length=1000)
    agent_instructions: str = Field(default="", max_length=2000)
    notifications_enabled: bool = True


class RoleUpdate(StrictModel):
    """Owner-assigned permissions for operational staff roles."""

    permissions: list[str] = Field(max_length=30)


class AgentConfig(StrictModel):
    """Owner-controlled model behavior without browser-visible credentials."""

    model: str = Field(default="", max_length=100)
    daily_tokens: int = Field(default=50000, ge=1000, le=1000000)
    max_iterations: int = Field(default=4, ge=1, le=6)
    input_price: float = Field(default=0, ge=0, le=10000, allow_inf_nan=False)
    output_price: float = Field(default=0, ge=0, le=10000, allow_inf_nan=False)
