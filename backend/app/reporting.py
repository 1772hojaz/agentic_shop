"""Authoritative sales aggregates and dashboard metrics."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import utcnow
from app.models import (
    Category,
    Customer,
    Inventory,
    Order,
    OrderItem,
    Payment,
    Product,
    Variant,
)


def sales_report(db: Session, days: int = 30) -> dict:
    """Calculate revenue from settled payments, never pending orders."""
    since = utcnow() - timedelta(days=days)
    paid = (
        select(Payment)
        .where(Payment.status == "paid", Payment.created_at >= since)
        .subquery()
    )
    revenue = db.scalar(select(func.coalesce(func.sum(paid.c.amount), 0)))
    count = db.scalar(select(func.count()).select_from(paid))
    trend = db.execute(
        select(
            func.date(paid.c.created_at).label("date"),
            func.sum(paid.c.amount).label("revenue"),
        )
        .group_by(func.date(paid.c.created_at))
        .order_by("date")
    ).all()
    statuses = db.execute(
        select(Order.status, func.count())
        .where(Order.created_at >= since)
        .group_by(Order.status)
    ).all()
    return {
        "days": days,
        "revenue": revenue,
        "average_order_value": revenue / count if count else 0,
        "paid_transactions": count,
        "total_orders": sum(count for _, count in statuses),
        "order_statuses": dict(statuses),
        **shop_counts(db),
        "trend": [dict(row._mapping) for row in trend],
        "best_sellers": best_sellers(db, since),
        "category_sales": category_sales(db, since),
        "customer_activity": customer_activity(db, since),
    }


def shop_counts(db: Session) -> dict:
    """Return deployment-wide customer and availability signals."""
    return {
        "customers": db.scalar(select(func.count(Customer.id))),
        "products": db.scalar(
            select(func.count(Product.id)).where(Product.active.is_(True))
        ),
        "low_stock": db.scalar(
            select(func.count())
            .select_from(Inventory)
            .where(Inventory.quantity <= Inventory.low_stock_threshold)
        ),
    }


def best_sellers(db: Session, since) -> list[dict]:
    """Aggregate fulfilled or paid orders rather than abandoned carts."""
    rows = db.execute(
        select(
            OrderItem.name,
            func.sum(OrderItem.quantity).label("units"),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label("sales"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            Order.created_at >= since,
            Order.id.in_(
                select(Payment.order_id).where(Payment.status == "paid")
            ),
        )
        .group_by(OrderItem.name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(10)
    ).all()
    return [dict(row._mapping) for row in rows]


def category_sales(db: Session, since) -> list[dict]:
    """Group paid order snapshots by their catalogue category."""
    rows = db.execute(
        select(
            func.coalesce(Category.name, "Uncategorised").label("category"),
            func.sum(OrderItem.quantity).label("units"),
            func.sum(OrderItem.quantity * OrderItem.unit_price).label("sales"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .join(Variant, Variant.id == OrderItem.variant_id)
        .join(Product, Product.id == Variant.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(
            Order.created_at >= since,
            Order.id.in_(
                select(Payment.order_id).where(Payment.status == "paid")
            ),
        )
        .group_by(Category.name)
        .limit(100)
    ).all()
    return [dict(row._mapping) for row in rows]


def customer_activity(db: Session, since) -> list[dict]:
    """Aggregate purchasing activity without counting unpaid reservations."""
    rows = db.execute(
        select(
            Customer.name,
            func.count(Order.id).label("orders"),
            func.sum(Order.total).label("spend"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .where(
            Order.created_at >= since,
            Order.id.in_(
                select(Payment.order_id).where(Payment.status == "paid")
            ),
        )
        .group_by(Customer.id, Customer.name)
        .order_by(func.sum(Order.total).desc())
        .limit(20)
    ).all()
    return [dict(row._mapping) for row in rows]
