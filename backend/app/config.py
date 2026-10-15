"""Runtime configuration. Every value comes from the environment (or .env); nothing secret is a default."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres@localhost:5432/regengine"

    llm_provider: str = "anthropic"
    llm_model_id: str = "claude-opus-5-5"
    anthropic_api_key: SecretStr | None = None

    embedding_model: str = "nomic-ai/nomic-embed-text-v1.5"

    log_id_salt: SecretStr = SecretStr("dev-only-salt")

    # Polite access to public ArcGIS services.
    arcgis_page_delay_s: float = 0.25
    http_user_agent: str = "cover-regulatory-poc/0.1 (research prototype)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
