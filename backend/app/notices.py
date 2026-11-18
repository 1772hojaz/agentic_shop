"""Transactional notification helpers shared by commerce services."""

from sqlalchemy import select

from app.database import utcnow
from app.models import AdminBinding, Notification, ShopSetting


def enabled(db) -> bool:
    """Respect the owner's non-secret notification preference."""
    settings = db.get(ShopSetting, "shop")
    return not settings or settings.value.get("notifications_enabled", True)


def queue_text(db, phone: str, text: str) -> None:
    """Enqueue a WhatsApp text in the caller's business transaction."""
    if enabled(db):
        db.add(
            Notification(
                recipient=phone,
                content={"type": "text", "text": {"body": text[:4000]}},
            )
        )


def notify_admins(db, text: str) -> None:
    """Send operational notices only to currently paired administrators."""
    phones = db.scalars(
        select(AdminBinding.phone)
        .where(
            AdminBinding.used.is_(True),
            AdminBinding.phone.is_not(None),
            AdminBinding.expires_at > utcnow(),
        )
        .distinct()
    )
    for phone in phones:
        queue_text(db, phone, text)
