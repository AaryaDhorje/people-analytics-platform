"""Application configuration, loaded from environment variables.

Everything the app needs to run is declared here and nowhere else. A missing
required variable fails at import time with a readable error rather than at the
first request.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = "local"

    database_url: str = "postgresql+psycopg://people:people@localhost:5432/people_analytics"

    #: `NoDecode` is required, not decorative. Without it, pydantic-settings treats a
    #: list-typed field as a "complex" value and attempts json.loads() on the raw env
    #: string *before* any validator runs — so `CORS_ORIGINS=http://localhost:5173`
    #: raises SettingsError instead of reaching `_split_origins` below.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    demo_bearer_token: str = "dev-demo-token-change-me"

    anthropic_api_key: str | None = None
    model_reasoning: str = "claude-sonnet-5"
    model_bulk: str = "claude-haiku-4-5-20251001"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """Accept a comma-separated string so the value is easy to set in Render/Vercel."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @property
    def is_local(self) -> bool:
        return self.env == "local"


@lru_cache
def get_settings() -> Settings:
    """Cached so the env file is read once per process."""
    return Settings()


settings = get_settings()
