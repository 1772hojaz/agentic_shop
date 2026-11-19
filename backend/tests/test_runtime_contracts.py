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


def test_production_requires_secure_transport():
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    for secure, url in (
        (False, "https://shop.example"),
        (True, "http://shop.example"),
    ):
        with pytest.raises(ValidationError, match="HTTPS secure cookies"):
            Settings(
                _env_file=None,
                environment="production",
                database_url="postgresql://localhost/shop",
                cookie_secure=secure,
                public_url=url,
            )


def test_production_ai_transport():
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="model requests require HTTPS"):
        Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql://localhost/shop",
            cookie_secure=True,
            public_url="https://shop.example",
            ai_api_url="http://model.test",
        )
    assert Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql://localhost/shop",
        cookie_secure=True,
        public_url="https://shop.example",
        ai_api_url="https://model.test",
    )


def test_agent_work_limits():
    import pytest
    from pydantic import ValidationError

    from app.schemas import AgentConfig

    for field, values in (
        ("daily_tokens", (999, 1000001)),
        ("max_iterations", (0, 7)),
    ):
        for value in values:
            with pytest.raises(ValidationError):
                AgentConfig(**{field: value})
    assert AgentConfig(daily_tokens=1000, max_iterations=1)
    assert AgentConfig(daily_tokens=1000000, max_iterations=6)


def test_agent_prices_must_be_finite():
    import pytest
    from pydantic import ValidationError

    from app.schemas import AgentConfig

    for field in ("input_price", "output_price"):
        for value in (-1, 10001, float("nan"), float("inf")):
            with pytest.raises(ValidationError):
                AgentConfig(**{field: value})
        assert AgentConfig(**{field: 10000})


def test_liveness_is_public_and_minimal(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_http_security_headers(client):
    expected = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "referrer-policy": "same-origin",
        "cache-control": "no-store",
    }
    for path in ("/health", "/api/v1/staff", "/does-not-exist"):
        response = client.get(path)
        for key, value in expected.items():
            assert response.headers[key] == value


def test_http_body_size_boundary(client):
    for length in (str(6 * 1024 * 1024 + 1), "invalid", "-1"):
        response = client.get("/health", headers={"Content-Length": length})
        assert response.status_code == 413
        assert response.json() == {"detail": "Request too large"}
    assert (
        client.get("/health", headers={"Content-Length": "0"}).status_code
        == 200
    )


def test_http_rate_limit_contract(client):
    from app.main import limits

    for _ in range(180):
        assert client.get("/health").status_code == 200
    response = client.get("/health")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert response.json() == {"detail": "Rate limit exceeded"}
    limits.clear()


def test_login_validation_redacts_input(client):
    secret = "sensitive-password-" * 10
    response = client.post(
        "/api/v1/auth/login", json={"email": "a@b.test", "password": secret}
    )
    assert response.status_code == 422
    assert secret not in response.text
    assert response.json()["detail"] == "Invalid request"
    assert any(
        field["field"] == "body.password"
        for field in response.json()["fields"]
    )
