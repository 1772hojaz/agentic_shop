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


def test_staff_password_boundaries():
    import pytest
    from pydantic import ValidationError

    from app.schemas import StaffInput

    for size in (11, 129):
        with pytest.raises(ValidationError):
            StaffInput(email="a@b.test", name="Staff", password="x" * size)
    for size in (12, 128):
        assert StaffInput(email="a@b.test", name="Staff", password="x" * size)


def test_staff_roles_are_closed():
    import pytest
    from pydantic import ValidationError

    from app.schemas import StaffInput, StaffUpdate

    for role in ("admin", "superuser", "customer", ""):
        with pytest.raises(ValidationError):
            StaffUpdate(role=role)
        with pytest.raises(ValidationError):
            StaffInput(
                email="a@b.test", name="Staff", password="x" * 12, role=role
            )
