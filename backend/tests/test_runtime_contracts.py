"""Focused regression coverage for backend contracts."""


def test_production_requires_postgres(monkeypatch):
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    for url in ("sqlite:///shop.db", "mysql://localhost/shop"):
        with pytest.raises(ValidationError, match="PostgreSQL"):
            Settings(
                _env_file=None,
                environment="production",
                database_url=url,
                cookie_secure=True,
                public_url="https://shop.example",
            )
