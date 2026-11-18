"""Non-secret runtime agent controls with server environment defaults."""

from app.config import get_settings
from app.models import ShopSetting
from app.schemas import AgentConfig


def agent_config(db) -> AgentConfig:
    """Resolve current model and budget without returning API credentials."""
    settings = get_settings()
    values = {
        "model": settings.ai_model,
        "daily_tokens": settings.ai_daily_tokens,
        "max_iterations": settings.ai_max_iterations,
        "input_price": settings.ai_input_price,
        "output_price": settings.ai_output_price,
    }
    record = db.get(ShopSetting, "agent")
    if record:
        values.update(record.value)
    return AgentConfig.model_validate(values)
