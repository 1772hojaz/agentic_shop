"""Permission-aware tool execution and human-only confirmation dispatch."""

from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import Principal, request_confirmation
from app.catalogue import (
    cart_detail,
    create_product,
    get_record,
    move_stock,
    search_products,
    serialize,
    set_cart,
    update_product,
)
from app.database import audit, utcnow
from app.models import (
    Category,
    Confirmation,
    Customer,
    Inventory,
    Notification,
    Order,
    Payment,
    ShopSetting,
    Variant,
)
from app.orders import change_status, checkout, order_detail, visible_order
from app.payments import initiate_payment, refund_payment, settle_cash
from app.reporting import sales_report
from app.schemas import (
    AgentConfig,
    CartInput,
    CategoryInput,
    Checkout,
    NotificationInput,
    OrderStatus,
    PaymentInput,
    PriceInput,
    ProductChange,
    ProductInput,
    ProductUpdate,
    Search,
    SettingInput,
    StockInput,
    StrictModel,
    ThresholdInput,
)


class Empty(StrictModel):
    """A tool that accepts no model-supplied arguments."""


class RecordInput(StrictModel):
    """Opaque identifier for a permission-checked lookup."""

    id: str


@dataclass
class Tool:
    """Strict schema and permission attached to a business operation."""

    permission: str
    schema: type[StrictModel]
    handler: object
    description: str
    sensitive: bool = False


def inventory_lookup(db, actor, data):
    """Return catalogue stock without customer or supplier information."""
    query = select(Inventory).limit(50)
    if data.id:
        query = query.where(Inventory.variant_id == data.id)
    return [serialize(row) for row in db.scalars(query)]


def lookup_customer(db, actor, data):
    """Search contact information only for authorised administrators."""
    query = (
        select(Customer)
        .where(Customer.name.ilike("%" + data.name + "%"))
        .limit(30)
    )
    return [serialize(row) for row in db.scalars(query)]


def list_orders(db, actor, data):
    """Scope order lookup to the authenticated customer or staff role."""
    if data.id:
        return order_detail(db, visible_order(db, actor, data.id))
    query = select(Order).order_by(Order.created_at.desc()).limit(20)
    if actor.context == "customer":
        query = query.where(Order.customer_id == actor.id)
    return [serialize(row) for row in db.scalars(query)]


def lookup_payment(db, actor, data):
    """Read a payment only after checking its parent order ownership."""
    record = get_record(db, Payment, data.id)
    visible_order(db, actor, record.order_id)
    return serialize(record)


def update_price(db, actor, data):
    """Apply a precisely confirmed price using fixed-precision arithmetic."""
    variant = get_record(db, Variant, data.variant_id)
    variant.price = data.price
    audit(db, actor.id, "product.price", variant.id)
    return serialize(variant)


def update_threshold(db, actor, data):
    """Apply an exact low-stock threshold after explicit consent."""
    stock = get_record(db, Inventory, data.variant_id)
    stock.low_stock_threshold = data.threshold
    audit(db, actor.id, "inventory.threshold", data.variant_id)
    return serialize(stock)


def queue_notification(db, actor, data):
    """Create a durable WhatsApp notification for an existing customer."""
    customer = get_record(db, Customer, data.customer_id)
    notification = Notification(
        recipient=customer.phone,
        content=notification_content(data),
    )
    db.add(notification)
    db.flush()
    audit(db, actor.id, "notification.queue", notification.id)
    return serialize(notification)


def notification_content(data):
    """Build supported official Meta message types from validated fields."""
    if data.kind in {"image", "document"}:
        if not data.media_url.startswith("https://"):
            raise HTTPException(422, "Media messages require an HTTPS URL")
        return {
            "type": data.kind,
            data.kind: {
                "link": data.media_url,
                "caption": data.text[:1000],
            },
        }
    if data.kind == "template":
        if not data.template_name:
            raise HTTPException(422, "Approved template name required")
        return {
            "type": "template",
            "template": {
                "name": data.template_name,
                "language": {"code": data.language},
            },
        }
    if data.kind == "interactive":
        return support_button(data.text)
    return {"type": "text", "text": {"body": data.text}}


def support_button(text: str) -> dict:
    """Offer an interactive reply without model-generated consent."""
    reply = {"id": "I need shop support", "title": "Contact support"}
    return {
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": text[:1024]},
            "action": {"buttons": [{"type": "reply", "reply": reply}]},
        },
    }


def configure_agent(db, actor, data):
    """Persist non-secret agent controls after owner confirmation."""
    record = db.get(ShopSetting, "agent")
    if not record:
        record = ShopSetting(key="agent", value={})
        db.add(record)
    record.value = data.model_dump()
    audit(db, actor.id, "agent.configure", "agent")
    return record.value


def update_settings(db, actor, data):
    """Store only validated non-secret configuration."""
    record = db.get(ShopSetting, "shop")
    if not record:
        record = ShopSetting(key="shop", value={})
        db.add(record)
    record.value = data.model_dump()
    audit(db, actor.id, "settings.update", "shop")
    return record.value


