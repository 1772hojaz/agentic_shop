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


def make_engine(url: str):
    """Use a small connection pool and enforce SQLite foreign keys."""
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    else:
        options.update(pool_size=3, max_overflow=2)
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, record):
            """Match production foreign-key behavior during local tests."""
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    """Commit successful requests and roll back failed operations."""
    with SessionLocal() as session:
        with session.begin():
            yield session


def audit(db: Session, actor: str, action: str, entity: str) -> None:
    """Record a business action in the same database transaction."""
    from app.models import AuditLog

    db.add(AuditLog(actor_id=actor, action=action, entity_id=entity))
