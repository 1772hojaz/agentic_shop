"""Transactional checkout, fulfillment states and reservation release."""

from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.catalogue import get_record, move_stock, own_cart, serialize
from app.config import get_settings
from app.database import audit, utcnow
from app.models import (
    Cart,
    CartItem,
    Customer,
    Notification,
    Order,
    OrderItem,
    Payment,
    Product,
    Variant,
)
from app.schemas import Checkout, OrderStatus, StockInput

TRANSITIONS = {
    "pending_payment": {"paid", "processing", "cancelled", "expired"},
    "paid": {"processing", "refund_pending"},
    "processing": {"ready_for_delivery", "refund_pending", "cancelled"},
    "ready_for_delivery": {
        "out_for_delivery",
        "completed",
        "refund_pending",
        "cancelled",
    },
    "out_for_delivery": {"delivered", "delivery_failed", "cancelled"},
    "delivered": {"completed", "refund_pending"},
    "delivery_failed": {"out_for_delivery", "refund_pending", "cancelled"},
    "completed": {"refund_pending"},
    "refund_pending": {"refunded"},
    "cancelled": set(),
    "expired": set(),
    "refunded": set(),
}


def visible_order(db: Session, actor: Principal, order_id: str) -> Order:
    """Hide other customers' orders even when their UUID is known."""
    order = get_record(db, Order, order_id)
    if actor.context == "customer":
        actor.require("orders.own")
        if order.customer_id != actor.id:
            raise HTTPException(404, "Record not found")
    else:
        actor.require("orders.read")
    return order


def order_detail(db: Session, order: Order) -> dict:
    """Return immutable line items and separate payment records."""
    result = serialize(order)
    result["items"] = [
        serialize(row)
        for row in db.scalars(
            select(OrderItem).where(OrderItem.order_id == order.id)
        )
    ]
    result["payments"] = [
        serialize(row)
        for row in db.scalars(
            select(Payment).where(Payment.order_id == order.id)
        )
    ]
    return result


def checkout(db: Session, actor: Principal, data: Checkout) -> dict:
    """Reserve stock and create an unpaid order atomically."""
    cart = own_cart(db, actor)
    db.scalar(select(Cart).where(Cart.id == cart.id).with_for_update())
    existing = db.scalar(
        select(Order).where(Order.checkout_key == data.checkout_key)
    )
    if existing:
        return order_detail(db, visible_order(db, actor, existing.id))
    if data.method == "delivery" and not data.address:
        raise HTTPException(422, "Delivery address required")
    items = db.scalars(
        select(CartItem)
        .where(CartItem.cart_id == cart.id)
        .order_by(CartItem.variant_id)
    ).all()
    if not items:
        raise HTTPException(409, "Cart is empty")
    order = Order(
        customer_id=actor.id,
        total=Decimal("0"),
        currency=get_settings().currency.upper(),
        delivery=data.model_dump(exclude={"checkout_key"}),
        checkout_key=data.checkout_key,
        expires_at=utcnow() + timedelta(hours=24),
    )
    db.add(order)
    db.flush()
    for item in items:
        add_order_line(db, actor, order, item)
    db.execute(delete(CartItem).where(CartItem.cart_id == cart.id))
    audit(db, actor.id, "order.create", order.id)
    order_notification(db, order)
    from app.notices import notify_admins

    notify_admins(db, f"New order {order.id}: {order.currency} {order.total}.")
    db.flush()
    return order_detail(db, order)


def add_order_line(db, actor, order, item) -> None:
    """Snapshot one variant and reserve its available stock."""
    variant = get_record(db, Variant, item.variant_id)
    product = get_record(db, Product, variant.product_id)
    if not product.active:
        raise HTTPException(409, "A cart product is no longer available")
    move_stock(
        db,
        actor.id,
        StockInput(
            variant_id=variant.id,
            delta=-item.quantity,
            reason=f"Order {order.id}",
        ),
    )
    db.add(
        OrderItem(
            order_id=order.id,
            variant_id=variant.id,
            name=f"{product.name} {variant.options}",
            unit_price=variant.price,
            quantity=item.quantity,
        )
    )
    order.total += variant.price * item.quantity


def change_status(db: Session, actor: Principal, data: OrderStatus) -> dict:
    """Execute an authorised fulfillment transition after confirmation."""
    actor.require("orders.write")
    order = db.scalar(
        select(Order).where(Order.id == data.order_id).with_for_update()
    )
    if not order:
        raise HTTPException(404, "Record not found")
    transition(db, order, data.status, actor.id)
    if data.tracking:
        order.delivery = {**order.delivery, "tracking": data.tracking}
    return order_detail(db, order)


def transition(db, order: Order, target: str, actor_id: str) -> None:
    """Enforce the state graph, preserving stock and payment boundaries."""
    if target not in TRANSITIONS.get(order.status, set()):
        raise HTTPException(409, f"Cannot move {order.status} to {target}")
    validate_payment_boundary(db, order, target)
    if target in {"cancelled", "expired"}:
        release_stock(db, order, actor_id)
    order.status = target
    audit(db, actor_id, f"order.{target}", order.id)
    order_notification(db, order)
    db.flush()


def validate_payment_boundary(db, order: Order, target: str) -> None:
    """Allow unpaid cash fulfillment without pretending money was received."""
    settled = db.scalar(
        select(Payment.id).where(
            Payment.order_id == order.id, Payment.status == "paid"
        )
    )
    if target in {"completed", "refund_pending"} and not settled:
        raise HTTPException(409, "This transition requires a settled payment")
    if target in {"cancelled", "expired"} and settled:
        raise HTTPException(409, "Settled orders require a refund")
    if order.status == "pending_payment" and target == "processing":
        cash = db.scalar(
            select(Payment.id).where(
                Payment.order_id == order.id,
                Payment.method == "cash",
                Payment.status == "pending",
            )
        )
        if not cash:
            raise HTTPException(409, "Payment or cash arrangement required")


def release_stock(db: Session, order: Order, actor_id: str) -> None:
    """Return an unpaid order's reserved stock exactly once."""
    items = db.scalars(
        select(OrderItem)
        .where(OrderItem.order_id == order.id)
        .order_by(OrderItem.variant_id)
    )
    for item in items:
        move_stock(
            db,
            actor_id,
            StockInput(
                variant_id=item.variant_id,
                delta=item.quantity,
                reason=f"Release {order.id}",
            ),
        )


def order_notification(db: Session, order: Order) -> None:
    """Queue a customer update in the order transaction."""
    customer = db.get(Customer, order.customer_id)
    from app.notices import enabled

    if customer and enabled(db):
        db.add(
            Notification(
                recipient=customer.phone,
                content={
                    "type": "text",
                    "text": {
                        "body": (
                            f"Order {order.id}: "
                            f"{order.status.replace('_', ' ')}. "
                            f"Total {order.currency} {order.total:.2f}."
                        )
                    },
                },
            )
        )
