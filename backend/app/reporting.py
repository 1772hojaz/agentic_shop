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


