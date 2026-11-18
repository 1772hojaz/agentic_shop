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


