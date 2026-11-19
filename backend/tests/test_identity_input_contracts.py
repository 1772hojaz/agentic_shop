"""Focused regression coverage for backend contracts."""


def test_login_rejects_identity_overrides():
    import pytest
    from pydantic import ValidationError

    from app.schemas import Login

    for field in ("role", "user_id", "permissions"):
        with pytest.raises(ValidationError):
            Login(
                email="a@example.test", password="secret", **{field: "owner"}
            )
