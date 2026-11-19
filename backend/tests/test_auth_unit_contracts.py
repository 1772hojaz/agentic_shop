"""Focused regression coverage for backend contracts."""


def test_password_hashes_use_independent_salts():
    from app.auth import hash_password, verify_password

    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert verify_password("correct horse battery staple", second)
    assert "correct horse battery staple" not in first


def test_wrong_password_is_rejected():
    from app.auth import hash_password, verify_password

    stored = hash_password("correct-password")
    for password in (
        "wrong-password",
        "",
        "Correct-password",
        "correct-password ",
    ):
        assert not verify_password(password, stored)


def test_malformed_password_hashes_fail_closed():
    from app.auth import verify_password

    for stored in (
        "",
        "plain-text",
        "scrypt$missing",
        "scrypt$a$b$c",
        "md5$a$b",
        "scrypt$salt$invalid",
    ):
        assert not verify_password("password", stored)


def test_unicode_password_round_trip():
    from app.auth import hash_password, verify_password

    password = "ijambo-ryibanga-é☃"
    stored = hash_password(password)
    assert verify_password(password, stored)
    assert not verify_password("ijambo-ryibanga-e", stored)


def test_principal_requires_explicit_permission():
    import pytest
    from fastapi import HTTPException

    from app.auth import Principal

    actor = Principal("user", "admin", {"products.read"})
    assert actor.require("products.read") is None
    for permission in ("products.write", "staff.write", "unknown"):
        with pytest.raises(HTTPException) as error:
            actor.require(permission)
        assert error.value.status_code == 403


def test_manager_defaults_exclude_owner_powers():
    from app.auth import PERMISSIONS, role_defaults

    grants = role_defaults("manager")
    assert "staff.write" not in grants
    assert "settings.write" not in grants
    assert grants == PERMISSIONS - {"staff.write", "settings.write"}


def test_staff_defaults_are_operational_only():
    from app.auth import role_defaults

    assert role_defaults("staff") == {
        "products.read",
        "orders.read",
        "orders.write",
        "ai.chat",
    }
