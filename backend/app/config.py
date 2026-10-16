"""Runtime configuration. Every value comes from the environment (or .env); nothing secret is a default."""

from functools import lru_cache

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres@localhost:5432/regengine"

    llm_provider: str = "anthropic"
    llm_model_id: str = "claude-opus-5-5"
    # The project environment provides ANTHROPIC_COVER_API_KEY; ANTHROPIC_API_KEY also works locally.
    anthropic_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("ANTHROPIC_COVER_API_KEY", "ANTHROPIC_API_KEY")
    )

    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"

    # Admin review screen. Both must be set or the admin endpoints stay disabled (503).
    # The hash is "scrypt$<salt hex>$<hash hex>"; create one with `python -m app.api.auth`.
    admin_username: str | None = None
    admin_password_scrypt: SecretStr | None = None

    # Hosted demo gate. When set, every /api route except health and the invite check needs the invite cookie.
    demo_invite_code: SecretStr | None = None

    @field_validator("anthropic_api_key", "admin_password_scrypt", "demo_invite_code", mode="before")
    @classmethod
    def _empty_is_unset(cls, v):
        # docker compose passes unset variables as "", which must mean "not configured", not an empty secret.
        return None if v == "" else v

    # Feedback older than this many days is deleted by `python -m app.api.purge`.
    feedback_retention_days: int = 14

    # Polite access to public ArcGIS services.
    arcgis_page_delay_s: float = 0.25
    http_user_agent: str = "cover-regulatory-poc/0.1 (research prototype)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
