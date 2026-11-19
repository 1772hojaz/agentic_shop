"""Focused regression coverage for backend contracts."""


def test_password_hashes_use_independent_salts():
    from app.auth import hash_password, verify_password

    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")
    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert verify_password("correct horse battery staple", second)
    assert "correct horse battery staple" not in first
