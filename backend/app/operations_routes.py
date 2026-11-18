"""Reporting, customer care, agent control and operational audit APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.agent import chat
from app.agent_config import agent_config
from app.auth import current_principal, require
from app.catalogue import get_record, page, serialize
from app.config import get_settings
from app.database import get_db
from app.models import (
    AIUsage,
    AuditLog,
    Confirmation,
    Conversation,
    Customer,
    Message,
    Notification,
    Order,
    ShopSetting,
    WebhookJob,
)
from app.registry import confirm_action, execute_tool
from app.reporting import sales_report
from app.schemas import AgentConfig, ChatInput, NotificationInput, SettingInput

router = APIRouter(prefix="/api/v1", tags=["Operations"])


@router.get("/ai/config")
def get_agent_config(
    actor=Depends(require("settings.write")), db=Depends(get_db)
):
    """Return editable non-secret model, budget and price controls."""
    return agent_config(db)


@router.put("/ai/config")
def save_agent_config(
    data: AgentConfig,
    actor=Depends(require("settings.write")),
    db=Depends(get_db),
):
    """Require human consent before changing model or spending controls."""
    return execute_tool(db, actor, "agent_configure", data.model_dump())


@router.get("/shop")
def public_shop():
    """Expose non-secret deployment currency to all client roles."""
    return {"currency": get_settings().currency.upper()}


@router.get("/customers")
def customers(
    query: str = Query("", max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor=Depends(require("customers.read")),
    db=Depends(get_db),
):
    """Search customer contacts for authorised administrators."""
    statement = select(Customer).order_by(Customer.created_at.desc())
    if query:
        statement = statement.where(Customer.name.ilike("%" + query + "%"))
    return page(db, statement, offset, limit)


@router.get("/customers/{customer_id}")
def customer(
    customer_id: str,
    actor=Depends(require("customers.read")),
    db=Depends(get_db),
):
    """Retrieve customer contact information and recent order history."""
    record = get_record(db, Customer, customer_id)
    result = serialize(record)
    result["orders"] = page(
        db,
        select(Order)
        .where(Order.customer_id == customer_id)
        .order_by(Order.created_at.desc()),
        0,
        100,
    )["items"]
    return result


@router.get("/reports/sales")
@router.get("/reports/products")
@router.get("/reports/orders")
def reports(
    days: int = Query(30, ge=1, le=366),
    actor=Depends(require("reports.read")),
    db=Depends(get_db),
):
    """Return live revenue, order status and product sales aggregates."""
    return sales_report(db, days)


@router.post("/ai/chat")
def ai_chat(
    data: ChatInput, actor=Depends(require("ai.chat")), db=Depends(get_db)
):
    """Use the single orchestrator with a backend-selected context."""
    return chat(db, actor, data)


@router.get("/ai/usage")
def ai_usage(
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor=Depends(require("ai.read")),
    db=Depends(get_db),
):
    """Show measured provider usage and estimated costs."""
    result = page(
        db, select(AIUsage).order_by(AIUsage.created_at.desc()), offset, limit
    )
    result["input_tokens"] = db.scalar(
        select(func.coalesce(func.sum(AIUsage.input_tokens), 0))
    )
    result["output_tokens"] = db.scalar(
        select(func.coalesce(func.sum(AIUsage.output_tokens), 0))
    )
    result["estimated_cost"] = db.scalar(
        select(func.coalesce(func.sum(AIUsage.estimated_cost), 0))
    )
    return result


@router.get("/conversations")
def conversations(
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    actor=Depends(require("ai.read")),
    db=Depends(get_db),
):
    """Monitor customer and administrator conversation metadata."""
    return page(
        db,
        select(Conversation).order_by(Conversation.created_at.desc()),
        offset,
        limit,
    )


@router.get("/conversations/{conversation_id}")
def conversation(
    conversation_id: str,
    actor=Depends(require("ai.read")),
    db=Depends(get_db),
):
    """Retrieve conversation messages for authorised monitoring staff."""
    get_record(db, Conversation, conversation_id)
    return page(
        db,
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc()),
        0,
        100,
    )


