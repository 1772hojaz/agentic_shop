"""Alembic environment using the same validated database configuration."""

from alembic import context

from app import models  # noqa: F401
from app.database import Base, engine


def run_migrations():
    """Compare application metadata and apply versioned schema changes."""
    if context.is_offline_mode():
        context.configure(
            url=str(engine.url),
            target_metadata=Base.metadata,
            literal_binds=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
