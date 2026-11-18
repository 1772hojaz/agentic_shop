"""Database engine and request transaction boundaries."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


def utcnow() -> datetime:
    """Return naive UTC for consistent SQL timestamp storage."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    """Generate an opaque identifier without database coordination."""
    return str(uuid4())


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative metadata."""


