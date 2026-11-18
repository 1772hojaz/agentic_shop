"""Token-accounting and administrator tool transaction regressions."""

from app.auth import user_principal
from app.models import Product, User
from app.registry import confirm_action, execute_tool


def test_budget_stop_preserves_provider_usage(client, headers, monkeypatch):
    from app import agent
    from app.config import get_settings

    config = get_settings()
    monkeypatch.setattr(config, "ai_api_key", "test-key")
    monkeypatch.setattr(config, "ai_model", "test-model")
    monkeypatch.setattr(config, "ai_daily_tokens", 1000)

    def response(history, tools, model):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-budget",
                                "type": "function",
                                "function": {
                                    "name": "category_browse",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 1001, "completion_tokens": 1},
        }

    monkeypatch.setattr(agent, "model_request", response)
    result = client.post(
        "/api/v1/ai/chat",
        headers=headers["owner"],
        json={"message": "Browse categories"},
    )
    assert result.status_code == 200, result.text
    assert "budget exhausted" in result.json()["message"]
    usage = client.get("/api/v1/ai/usage", headers=headers["owner"]).json()
    assert usage["input_tokens"] == 1001
    assert (
        client.post(
            "/api/v1/ai/chat",
            headers=headers["owner"],
            json={"message": "Try again"},
        ).status_code
        == 429
    )


def test_admin_product_creation_uses_exact_confirmation(store, identities):
    with store.begin() as db:
        owner = db.get(User, identities["owner"]["id"])
        actor = user_principal(db, owner)
        pending = execute_tool(
            db,
            actor,
            "product_create",
            {
                "name": "Confirmed catalogue item",
                "variants": [
                    {"sku": "CONFIRMED-1", "price": "8.00", "quantity": 4}
                ],
            },
        )
        assert db.query(Product).count() == 0
        result = confirm_action(db, actor, pending["id"])
        assert result["name"] == "Confirmed catalogue item"
        assert db.query(Product).count() == 1
