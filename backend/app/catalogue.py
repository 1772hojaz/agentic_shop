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


def create_product(db: Session, actor: Principal, data: ProductInput) -> dict:
    """Create a product, variants and traceable opening stock together."""
    actor.require("products.write")
    if any(option.quantity for option in data.variants):
        actor.require("inventory.write")
    if data.category_id:
        get_record(db, Category, data.category_id)
    product = Product(**data.model_dump(exclude={"variants"}))
    db.add(product)
    db.flush()
    for option in data.variants:
        variant = Variant(
            product_id=product.id,
            **option.model_dump(exclude={"quantity", "low_stock_threshold"}),
        )
        db.add(variant)
        db.flush()
        db.add(
            Inventory(
                variant_id=variant.id,
                quantity=option.quantity,
                low_stock_threshold=option.low_stock_threshold,
            )
        )
        db.add(
            StockMovement(
                variant_id=variant.id,
                delta=option.quantity,
                reason="Opening balance",
                actor_id=actor.id,
            )
        )
    audit(db, actor.id, "product.create", product.id)
    db.flush()
    return product_detail(db, product)


def update_product(db, actor, product_id: str, data) -> dict:
    """Edit catalogue fields through the same service for web and tools."""
    actor.require("products.write")
    record = get_record(db, Product, product_id)
    if data.category_id:
        get_record(db, Category, data.category_id)
    for key, value in data.model_dump().items():
        setattr(record, key, value)
    audit(db, actor.id, "product.update", record.id)
    return product_detail(db, record)


def move_stock(db: Session, actor_id: str, data: StockInput) -> dict:
    """Apply a conditional atomic adjustment without allowing overselling."""
    statement = (
        update(Inventory)
        .where(
            Inventory.variant_id == data.variant_id,
            Inventory.quantity + data.delta >= 0,
        )
        .values(quantity=Inventory.quantity + data.delta)
    )
    result = db.execute(statement)
    if result.rowcount != 1:
        raise HTTPException(409, "Insufficient stock or unknown variant")
    db.add(
        StockMovement(
            variant_id=data.variant_id,
            delta=data.delta,
            reason=data.reason,
            actor_id=actor_id,
        )
    )
    audit(db, actor_id, "inventory.adjust", data.variant_id)
    db.flush()
    stock = get_record(db, Inventory, data.variant_id)
    if data.delta < 0 and stock.quantity <= stock.low_stock_threshold:
        from app.notices import notify_admins

        notify_admins(
            db, f"Low stock: {data.variant_id}, {stock.quantity} left."
        )
    return serialize(stock)


def own_cart(db: Session, actor: Principal) -> Cart:
    """Resolve a cart from authenticated ownership only."""
    actor.require("cart.own")
    cart = db.scalar(select(Cart).where(Cart.customer_id == actor.id))
    if not cart:
        cart = Cart(customer_id=actor.id)
        db.add(cart)
        db.flush()
    return cart


def cart_detail(db: Session, actor: Principal) -> dict:
    """Calculate a personal cart from current authoritative prices."""
    cart = own_cart(db, actor)
    rows = db.execute(
        select(CartItem, Variant, Product)
        .join(Variant, Variant.id == CartItem.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .where(CartItem.cart_id == cart.id)
    ).all()
    items = [
        {
            "variant_id": variant.id,
            "name": product.name,
            "options": variant.options,
            "unit_price": variant.price,
            "quantity": item.quantity,
            "subtotal": variant.price * item.quantity,
        }
        for item, variant, product in rows
    ]
    return {
        "id": cart.id,
        "items": items,
        "total": sum((item["subtotal"] for item in items), Decimal("0")),
    }


def set_cart(db: Session, actor: Principal, data: CartInput) -> dict:
    """Set a personal cart quantity after validating product availability."""
    cart = own_cart(db, actor)
    db.scalar(select(Cart).where(Cart.id == cart.id).with_for_update())
    variant = get_record(db, Variant, data.variant_id)
    product = get_record(db, Product, variant.product_id)
    stock = get_record(db, Inventory, variant.id)
    if data.quantity and (
        not product.active or stock.quantity < data.quantity
    ):
        raise HTTPException(409, "Requested product quantity unavailable")
    db.execute(
        delete(CartItem).where(
            CartItem.cart_id == cart.id, CartItem.variant_id == variant.id
        )
    )
    if data.quantity:
        db.add(
            CartItem(
                cart_id=cart.id, variant_id=variant.id, quantity=data.quantity
            )
        )
    db.flush()
    return cart_detail(db, actor)
