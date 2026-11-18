"""Relational records for identity, commerce, and integration delivery."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, new_id, utcnow


class Record:
    """Common opaque identity and creation time."""

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=new_id
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class User(Record, Base):
    """An administrator or staff member with a hashed password."""

    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Role(Record, Base):
    """A named collection of operational permissions."""

    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(40), unique=True)


class Permission(Base):
    """A granular backend capability."""

    __tablename__ = "permissions"
    name: Mapped[str] = mapped_column(String(60), primary_key=True)


class UserRole(Base):
    """Assign a user to a role."""

    __tablename__ = "user_roles"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id"), primary_key=True
    )


class RolePermission(Base):
    """Grant one permission to a role."""

    __tablename__ = "role_permissions"
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.id"), primary_key=True
    )
    permission: Mapped[str] = mapped_column(
        ForeignKey("permissions.name"), primary_key=True
    )


class Customer(Record, Base):
    """Customer identity resolved from a verified messaging sender."""

    __tablename__ = "customers"
    phone: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(100), default="Customer")


class AuthSession(Base):
    """Revocable session; only a SHA-256 token digest is stored."""

    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    csrf: Mapped[str] = mapped_column(String(64))


class AdminBinding(Record, Base):
    """Expiring WhatsApp pairing obtained from an authenticated session."""

    __tablename__ = "admin_bindings"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    phone: Mapped[str | None] = mapped_column(String(30), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Category(Record, Base):
    """Product grouping used by catalogue and sales reports."""

    __tablename__ = "categories"
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Product(Record, Base):
    """Catalogue information; sellable options live in variants."""

    __tablename__ = "products"
    name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id")
    )
    image_url: Mapped[str] = mapped_column(String(500), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Variant(Record, Base):
    """A priced, independently stocked product option."""

    __tablename__ = "product_variants"
    __table_args__ = (CheckConstraint("price >= 0"),)
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id"), index=True
    )
    sku: Mapped[str] = mapped_column(String(100), unique=True)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2))


class Inventory(Base):
    """Available units with a low-stock threshold."""

    __tablename__ = "inventory"
    __table_args__ = (
        CheckConstraint("quantity >= 0"),
        CheckConstraint("low_stock_threshold >= 0"),
    )
    variant_id: Mapped[str] = mapped_column(
        ForeignKey("product_variants.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=5)


class StockMovement(Record, Base):
    """Append-only stock delta with reason and actor."""

    __tablename__ = "stock_movements"
    variant_id: Mapped[str] = mapped_column(
        ForeignKey("product_variants.id"), index=True
    )
    delta: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(200))
    actor_id: Mapped[str] = mapped_column(String(36))


class Cart(Record, Base):
    """One reusable shopping cart per customer."""

    __tablename__ = "carts"
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id"), unique=True
    )


class CartItem(Base):
    """Positive product quantity in a personal cart."""

    __tablename__ = "cart_items"
    __table_args__ = (CheckConstraint("quantity > 0"),)
    cart_id: Mapped[str] = mapped_column(
        ForeignKey("carts.id"), primary_key=True
    )
    variant_id: Mapped[str] = mapped_column(
        ForeignKey("product_variants.id"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer)


class Order(Record, Base):
    """Order fulfillment state, separate from provider payment state."""

    __tablename__ = "orders"
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending_payment")
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    delivery: Mapped[dict] = mapped_column(JSON, default=dict)
    checkout_key: Mapped[str] = mapped_column(String(100), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class OrderItem(Record, Base):
    """Immutable name, option and price snapshot at checkout."""

    __tablename__ = "order_items"
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id"))
    name: Mapped[str] = mapped_column(String(250))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    quantity: Mapped[int] = mapped_column(Integer)


class Payment(Record, Base):
    """A payment attempt that never stores customer payment secrets."""

    __tablename__ = "payments"
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    method: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="pending")
    reference: Mapped[str | None] = mapped_column(String(200), unique=True)
    checkout_url: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    provider_attempts: Mapped[int] = mapped_column(Integer, default=0)
    provider_error: Mapped[str] = mapped_column(String(200), default="")


class PaymentEvent(Base):
    """Unique verified provider event used for replay prevention."""

    __tablename__ = "payment_events"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Conversation(Record, Base):
    """A private channel history tied to one principal."""

    __tablename__ = "conversations"
    principal_id: Mapped[str] = mapped_column(String(36), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="web")
    context: Mapped[str] = mapped_column(String(20))


class Message(Record, Base):
    """Bounded textual history and external delivery status."""

    __tablename__ = "messages"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    external_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="received")


class AgentSession(Record, Base):
    """Summary of older messages scoped to one conversation."""

    __tablename__ = "agent_sessions"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), unique=True
    )
    summary: Mapped[str] = mapped_column(Text, default="")


class AIUsage(Record, Base):
    """Provider-reported tokens and configured estimated spend."""

    __tablename__ = "ai_usage"
    principal_id: Mapped[str] = mapped_column(String(36), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id")
    )
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(16, 8))


class Confirmation(Record, Base):
    """Single-use consent bound to an exact action and principal."""

    __tablename__ = "confirmations"
    principal_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)


class Notification(Record, Base):
    """Durable outbound delivery with bounded retry state."""

    __tablename__ = "notifications"
    recipient: Mapped[str] = mapped_column(String(30))
    content: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    error: Mapped[str] = mapped_column(String(200), default="")
    external_id: Mapped[str | None] = mapped_column(String(200), unique=True)


class WebhookJob(Record, Base):
    """Durable deduplicated incoming Meta message."""

    __tablename__ = "webhook_jobs"
    external_id: Mapped[str] = mapped_column(String(200), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    error: Mapped[str] = mapped_column(String(200), default="")


class AuditLog(Record, Base):
    """Non-secret administrative action history."""

    __tablename__ = "audit_logs"
    actor_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(100))


class ShopSetting(Base):
    """Non-secret runtime settings for the shop and agent."""

    __tablename__ = "shop_settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class LoginAttempt(Base):
    """Database-backed rate limit window shared across restarts."""

    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    reset_at: Mapped[datetime] = mapped_column(DateTime)
