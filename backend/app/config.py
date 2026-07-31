"""Application configuration, loaded from environment variables.

Everything the app needs to run is declared here and nowhere else. A missing
required variable fails at import time with a readable error rather than at the
first request.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

#: provider -> (reasoning model, bulk model). Reasoning drives NL->SQL and narrative; bulk
#: classifies ~2,400 survey comments, where cost per token matters and the task is easy.
#:
#: The Gemini pair was chosen by *calling* every candidate, not by reading the model list,
#: because the list is not a capability check. `models.list` on this key advertises
#: `gemini-2.5-pro` and `gemini-2.5-flash`; generateContent then returns 404 "no longer
#: available to new users" for the flash and 429 RESOURCE_EXHAUSTED for every `pro`, which
#: carries no free-tier quota. Flash-class models are what a free key can actually run.
#:
#: **The free tier is 20 requests per day, per model, per project** — not per minute. The
#: quota id is `GenerateRequestsPerDayPerProjectPerModel-FreeTier`. Two consequences worth
#: knowing before a demo:
#:
#:   - `ai_cache` is not an optimisation here, it is the only thing that makes the feature
#:     usable. Twenty uncached questions exhausts a model for the day.
#:   - Each model has its own bucket, so exhausting the reasoning model does not touch the
#:     bulk one, and pointing MODEL_REASONING at a different model buys another 20.
#:     `python -m app.ai.prewarm` fills the demo path; run it well before recording.
#:
#: Override per environment with MODEL_REASONING / MODEL_BULK. Re-probe before relying on
#: these: both vendors retire ids on their own schedule, and BUILD_PLAN section 0 says the
#: same thing about the Claude pair.
AI_PROVIDERS: dict[str, tuple[str, str]] = {
    "anthropic": ("claude-sonnet-5", "claude-haiku-4-5-20251001"),
    "gemini": ("gemini-3.6-flash", "gemini-3.5-flash-lite"),
}


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

    #: Matched against the Origin header in addition to `cors_origins`. Vercel gives every
    #: preview deployment a unique hostname, so an exact-match list covers production only.
    #: Empty string disables it — FastAPI treats None and "" alike here.
    cors_origin_regex: str | None = None

    demo_bearer_token: str = "dev-demo-token-change-me"

    # --- AI layer (phase 6) --------------------------------------------------
    #
    # Two providers are supported behind one seam because the build has a Gemini key and
    # not a Claude one, and that could change before the deadline. `app/ai/` reads
    # `ai_provider` and the two model names; nothing else in the codebase knows which
    # vendor is answering. Switching is an env-var edit, not a code change.

    anthropic_api_key: str | None = None
    google_api_key: str | None = None

    #: Explicit override. Left unset, `resolved_ai_provider` picks whichever key exists.
    ai_provider: str | None = None

    #: Deliberately empty here rather than defaulted to a Claude model string. A default
    #: that names one vendor is wrong the moment the other is selected, and a wrong model
    #: id fails at the first API call rather than at startup. `resolved_models` fills these
    #: from the provider when they are not set.
    model_reasoning: str | None = None
    model_bulk: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        """Accept a comma-separated string so the value is easy to set in Render/Vercel."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    #: A declared-but-blank env var (`AI_PROVIDER=`) arrives as `""`, not as absent. Every
    #: field below means "unset" by that, and `""` is not a valid provider, not a valid key
    #: and not a valid model id — so normalise once here rather than defending against the
    #: empty string at each use.
    @field_validator(
        "ai_provider",
        "anthropic_api_key",
        "google_api_key",
        "model_reasoning",
        "model_bulk",
        "cors_origin_regex",
        mode="before",
    )
    @classmethod
    def _blank_is_unset(cls, v: object) -> object:
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("ai_provider")
    @classmethod
    def _known_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in AI_PROVIDERS:
            raise ValueError(f"AI_PROVIDER must be one of {sorted(AI_PROVIDERS)}, got {v!r}")
        return v

    @property
    def is_local(self) -> bool:
        return self.env == "local"

    @property
    def resolved_ai_provider(self) -> str | None:
        """Which vendor `app/ai/` should call, or None when the AI layer is unconfigured.

        An explicit `AI_PROVIDER` wins. Otherwise whichever key is present decides, so a
        working setup needs one variable rather than two kept in agreement. With both keys
        set and no explicit choice, Anthropic wins — BUILD_PLAN section 0 names it, and a
        silent coin-flip between vendors is worse than a stated preference.
        """
        if self.ai_provider:
            return self.ai_provider
        if self.anthropic_api_key:
            return "anthropic"
        if self.google_api_key:
            return "gemini"
        return None

    @property
    def ai_api_key(self) -> str | None:
        provider = self.resolved_ai_provider
        if provider == "anthropic":
            return self.anthropic_api_key
        if provider == "gemini":
            return self.google_api_key
        return None

    @property
    def resolved_models(self) -> tuple[str | None, str | None]:
        """(reasoning, bulk) model ids for the selected provider.

        Env vars override, because a model id outlives this file: both vendors rename and
        retire ids on their own schedule, and a deploy should not need a code change to
        follow. The defaults below are a starting point to confirm against the vendor's
        model list, not a guarantee.
        """
        provider = self.resolved_ai_provider
        default_reasoning, default_bulk = AI_PROVIDERS.get(provider or "", (None, None))
        return (
            self.model_reasoning or default_reasoning,
            self.model_bulk or default_bulk,
        )

    @property
    def ai_enabled(self) -> bool:
        """False means every AI route degrades to a clear message instead of a stack trace,
        which is the behaviour BUILD_PLAN phase 6 requires of a live demo."""
        return bool(self.ai_api_key)


@lru_cache
def get_settings() -> Settings:
    """Cached so the env file is read once per process."""
    return Settings()


settings = get_settings()
