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


class OptionalRecord(StrictModel):
    """A lookup of one record or a bounded list."""

    id: str = ""


def support_info(db) -> dict:
    """Expose public support details without internal agent instructions."""
    record = db.get(ShopSetting, "shop")
    values = record.value if record else {}
    keys = {"name", "contact", "delivery_instructions", "support_message"}
    return {key: values.get(key, "") for key in keys}


TOOLS = {
    "product_create": Tool(
        "products.write",
        ProductInput,
        create_product,
        "Create a product and variants after human confirmation.",
        True,
    ),
    "product_update": Tool(
        "products.write",
        ProductChange,
        lambda db, actor, data: update_product(
            db,
            actor,
            data.product_id,
            ProductUpdate.model_validate(
                data.model_dump(exclude={"product_id"})
            ),
        ),
        "Update product information after human confirmation.",
        True,
    ),
    "category_browse": Tool(
        "products.read",
        Empty,
        lambda db, actor, data: [
            serialize(row) for row in db.scalars(select(Category).limit(100))
        ],
        "List the shop's product categories.",
    ),
    "shop_support": Tool(
        "products.read",
        Empty,
        lambda db, actor, data: support_info(db),
        "Retrieve contact details, delivery and support instructions.",
    ),
    "stock_threshold": Tool(
        "inventory.write",
        ThresholdInput,
        update_threshold,
        "Configure a low-stock threshold after confirmation.",
        True,
    ),
    "payment_lookup": Tool(
        "orders.own",
        RecordInput,
        lookup_payment,
        "Check real payment status and checkout URL; initializing is unpaid.",
    ),
    "agent_configure": Tool(
        "settings.write",
        AgentConfig,
        configure_agent,
        "Change model, daily usage budget and cost estimates.",
        True,
    ),
    "payment_initiation": Tool(
        "orders.own",
        PaymentInput,
        initiate_payment,
        "Get cash instructions or a real hosted Stripe checkout URL.",
    ),
    "product_search": Tool(
        "products.read",
        Search,
        lambda db, actor, data: search_products(db, data),
        "Search current products, prices, variants and availability.",
    ),
    "inventory_lookup": Tool(
        "inventory.read",
        OptionalRecord,
        inventory_lookup,
        "Look up available stock; id is a variant ID or empty.",
    ),
    "cart_view": Tool(
        "cart.own",
        Empty,
        lambda db, actor, data: cart_detail(db, actor),
        "View the authenticated customer's personal cart.",
    ),
    "cart_management": Tool(
        "cart.own",
        CartInput,
        set_cart,
        "Set a personal cart item quantity; zero removes it.",
    ),
    "order_create": Tool(
        "orders.own",
        Checkout,
        checkout,
        "Create an unpaid order from the personal cart after user agreement.",
        True,
    ),
    "order_lookup": Tool(
        "orders.own",
        OptionalRecord,
        list_orders,
        "Retrieve personal orders; optional id selects one order.",
    ),
    "admin_orders": Tool(
        "orders.read",
        OptionalRecord,
        list_orders,
        "Retrieve shop orders for authorised staff.",
    ),
    "order_management": Tool(
        "orders.write",
        OrderStatus,
        change_status,
        "Request a fulfillment transition; requires human confirmation.",
        True,
    ),
    "sales_reporting": Tool(
        "reports.read",
        Empty,
        lambda db, actor, data: sales_report(db),
        "Retrieve the last 30 days of verified sales and order metrics.",
    ),
    "customer_lookup": Tool(
        "customers.read",
        CategoryInput,
        lookup_customer,
        "Search customers by name, for authorised administrators only.",
    ),
    "stock_adjustment": Tool(
        "inventory.write",
        StockInput,
        lambda db, actor, data: move_stock(db, actor.id, data),
        "Request a stock adjustment; requires human confirmation.",
        True,
    ),
    "product_price": Tool(
        "products.write",
        PriceInput,
        update_price,
        "Request an exact price change; requires human confirmation.",
        True,
    ),
    "notifications": Tool(
        "notifications.write",
        NotificationInput,
        queue_notification,
        "Request a customer notification; requires human confirmation.",
        True,
    ),
    "settings_update": Tool(
        "settings.write",
        SettingInput,
        update_settings,
        "Update shop settings after explicit confirmation.",
        True,
    ),
    "cash_settlement": Tool(
        "payments.write",
        RecordInput,
        lambda db, actor, data: settle_cash(db, actor, data.id),
        "Record actual receipt of a cash payment after confirmation.",
        True,
    ),
    "payment_refund": Tool(
        "payments.write",
        RecordInput,
        lambda db, actor, data: refund_payment(db, actor, data.id),
        "Refund a settled Stripe payment after confirmation.",
        True,
    ),
}


def execute_tool(
    db: Session, actor: Principal, name: str, arguments: dict
) -> dict:
    """Validate identity, permissions and parameters on every invocation."""
    tool = TOOLS.get(name)
    if not tool:
        raise HTTPException(422, "Unknown tool")
    actor.require(tool.permission)
    try:
        data = tool.schema.model_validate(arguments)
    except ValidationError as error:
        raise HTTPException(422, "Invalid tool parameters") from error
    if tool.sensitive:
        return request_confirmation(
            db, actor, name, data.model_dump(mode="json")
        )
    return tool.handler(db, actor, data)


def confirm_action(db: Session, actor: Principal, record_id: str) -> dict:
    """Consume exact consent atomically; unavailable as an AI tool."""
    record = db.get(Confirmation, record_id)
    if not record or record.principal_id != actor.id:
        raise HTTPException(404, "Confirmation not found")
    tool = TOOLS.get(record.action)
    if not tool:
        raise HTTPException(409, "Action no longer supported")
    actor.require(tool.permission)
    claimed = db.execute(
        update(Confirmation)
        .where(
            Confirmation.id == record.id,
            Confirmation.consumed.is_(False),
            Confirmation.expires_at > utcnow(),
        )
        .values(consumed=True)
    )
    if claimed.rowcount != 1:
        raise HTTPException(409, "Confirmation expired or already consumed")
    data = tool.schema.model_validate(record.payload)
    result = tool.handler(db, actor, data)
    audit(db, actor.id, "confirmation.execute", record.id)
    return result


def model_tools(actor: Principal) -> list[dict]:
    """Expose only tools allowed in this principal's current context."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": tool.description,
                "parameters": tool.schema.model_json_schema(),
            },
        }
        for name, tool in TOOLS.items()
        if tool.permission in actor.permissions
    ]
