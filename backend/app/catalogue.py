"""Product, variant, cart and inventory business services."""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth import Principal
from app.database import audit
from app.models import (
    Cart,
    CartItem,
    Category,
    Inventory,
    Product,
    StockMovement,
    Variant,
)
from app.schemas import CartInput, ProductInput, Search, StockInput


def get_record(db: Session, model, record_id: str):
    """Load one record or emit a consistent not-found response."""
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(404, "Record not found")
    return record


def serialize(record, exclude: set | None = None) -> dict:
    """Serialize mapped columns without relationships or private fields."""
    blocked = {"password_hash", "token_hash", "code_hash"} | (exclude or set())
    return {
        column.name: getattr(record, column.name)
        for column in record.__table__.columns
        if column.name not in blocked
    }


def page(db: Session, query, offset: int, limit: int) -> dict:
    """Return bounded records and a total count for dashboard pagination."""
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    records = db.scalars(query.offset(offset).limit(limit)).all()
    return {"items": [serialize(row) for row in records], "total": total}


def product_detail(db: Session, product: Product) -> dict:
    """Include priced variants and available stock in a catalogue response."""
    result = serialize(product)
    variants = db.scalars(
        select(Variant).where(Variant.product_id == product.id)
    )
    result["variants"] = []
    for variant in variants:
        item = serialize(variant)
        stock = db.get(Inventory, variant.id)
        item["quantity"] = stock.quantity if stock else 0
        result["variants"].append(item)
    return result


def search_products(
    db: Session,
    criteria: Search,
    offset: int = 0,
    limit: int = 30,
    include_archived: bool = False,
) -> dict:
    """Search live catalogue data using bound parameters."""
    query = select(Product).order_by(Product.created_at.desc())
    if not include_archived:
        query = query.where(Product.active.is_(True))
    if criteria.query:
        pattern = "%" + criteria.query.replace("%", "\\%") + "%"
        query = query.where(Product.name.ilike(pattern, escape="\\"))
    if criteria.category_id:
        query = query.where(Product.category_id == criteria.category_id)
    if criteria.max_price is not None:
        query = query.where(
            Product.id.in_(
                select(Variant.product_id).where(
                    Variant.price <= criteria.max_price
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    products = db.scalars(query.offset(offset).limit(limit))
    return {
        "items": [product_detail(db, row) for row in products],
        "total": total,
    }


