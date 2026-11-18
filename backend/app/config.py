"""Validated server-only configuration."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read deployment values without exposing credentials to clients."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./shop.db"
    public_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    session_hours: int = 8
    currency: str = "USD"
    upload_dir: str = "uploads"
    ai_api_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_input_price: float = 0
    ai_output_price: float = 0
    ai_daily_tokens: int = 50000
    ai_max_iterations: int = 4
    meta_access_token: str = ""
    meta_phone_id: str = ""
    meta_app_secret: str = ""
    meta_verify_token: str = ""
    meta_graph_version: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    @model_validator(mode="after")
    def validate_production(self):
        """Refuse insecure production transport and development storage."""
        if self.environment == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production requires PostgreSQL")
            if not self.cookie_secure or not self.public_url.startswith(
                "https://"
            ):
                raise ValueError("Production requires HTTPS secure cookies")
            if not self.ai_api_url.startswith("https://"):
                raise ValueError("Production model requests require HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process configuration once."""
    return Settings()
