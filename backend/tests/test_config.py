"""Configuration parsing.

These exist because of a real bug: `cors_origins` is a list-typed field, and
pydantic-settings treats list types as "complex", attempting `json.loads()` on the
raw environment value *before* any validator runs. A plain
`CORS_ORIGINS=http://localhost:5173` therefore raised `SettingsError` rather than
reaching the splitting validator.

It went unnoticed through all of phase 0 because no `.env` file existed, so the
field always fell back to its default. It surfaced the moment a real `.env` was
written — i.e. the first time the setting was actually used. Hence the tests.
"""

import pytest
from pydantic_settings import SettingsError

from app.config import Settings


def _settings(**overrides: str) -> Settings:
    """Build Settings from explicit env values, ignoring any real .env on disk."""
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


def test_cors_origins_accepts_a_comma_separated_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,https://b.example")

    assert _settings().cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_accepts_a_single_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression case: one bare URL, which is not valid JSON."""
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173")

    assert _settings().cors_origins == ["http://localhost:5173"]


def test_cors_origins_strips_whitespace_and_drops_blanks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " https://a.example , , https://b.example ")

    assert _settings().cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_falls_back_to_local_vite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert _settings().cors_origins == ["http://localhost:5173"]


def test_database_url_keeps_a_percent_encoded_password_intact() -> None:
    """A literal `#` in a password must be written as %23 in the URL, or everything
    from `#` onward is parsed as a fragment and the password silently truncates —
    which presents as an auth failure, not as a parsing error."""
    url = "postgresql+psycopg://postgres:Sec%23ret@localhost:5432/people_analytics"

    # Field name, not env-var name: `extra="ignore"` would silently drop DATABASE_URL
    # and the assertion would then pass or fail against the default value instead.
    settings = _settings(database_url=url)

    assert settings.database_url == url
    assert "%23" in settings.database_url


def test_settings_error_is_importable() -> None:
    """Guards the import used above: if pydantic-settings moves SettingsError, the
    tests that assert on parsing behaviour should fail loudly rather than skip."""
    assert issubclass(SettingsError, Exception)


# --- AI provider selection --------------------------------------------------
#
# The AI layer reads its vendor from config and nothing else in the codebase knows which
# one answers. That indirection is only safe if the resolution rules are pinned, because
# every way of getting them wrong fails at the first live API call — during the demo —
# rather than at startup.


def test_no_key_means_the_ai_layer_is_off() -> None:
    """Phase 6 requires every AI feature to degrade to a clear message. That path is only
    reachable if "unconfigured" is a state the app can report rather than crash on."""
    settings = _settings()

    assert settings.resolved_ai_provider is None
    assert settings.ai_enabled is False
    assert settings.resolved_models == (None, None)


def test_a_google_key_alone_selects_gemini_and_its_models() -> None:
    settings = _settings(google_api_key="test-key")

    assert settings.resolved_ai_provider == "gemini"
    assert settings.ai_api_key == "test-key"
    assert settings.resolved_models == ("gemini-2.5-pro", "gemini-2.5-flash")


def test_an_anthropic_key_alone_selects_claude_and_its_models() -> None:
    settings = _settings(anthropic_api_key="test-key")

    assert settings.resolved_ai_provider == "anthropic"
    assert settings.ai_api_key == "test-key"
    assert settings.resolved_models == ("claude-sonnet-5", "claude-haiku-4-5-20251001")


def test_both_keys_present_prefers_anthropic() -> None:
    """A stated preference beats a silent coin flip. BUILD_PLAN section 0 names Claude."""
    settings = _settings(anthropic_api_key="a", google_api_key="g")

    assert settings.resolved_ai_provider == "anthropic"
    assert settings.ai_api_key == "a"


def test_an_explicit_provider_overrides_key_precedence() -> None:
    settings = _settings(ai_provider="gemini", anthropic_api_key="a", google_api_key="g")

    assert settings.resolved_ai_provider == "gemini"
    assert settings.ai_api_key == "g"


def test_model_overrides_win_over_the_provider_defaults() -> None:
    """The trap this guards: `.env` carried MODEL_REASONING=claude-sonnet-5 from before the
    seam existed. Selecting Gemini would then have sent a Claude model id to Google and
    failed at the first call, with nothing in the config to explain why."""
    settings = _settings(
        google_api_key="g", model_reasoning="gemini-3-pro", model_bulk="gemini-3-flash"
    )

    assert settings.resolved_models == ("gemini-3-pro", "gemini-3-flash")


def test_an_unknown_provider_is_rejected_at_startup() -> None:
    """Fail on import with a readable error, not at the first request."""
    with pytest.raises(ValueError, match="AI_PROVIDER must be one of"):
        _settings(ai_provider="openai")


def test_blank_env_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """`.env` lists these keys with empty values so they are discoverable. A declared-but-
    blank variable arrives as `""`, not as absent, and `""` is not a valid provider — the
    whole test suite failed to import until this was normalised."""
    for name in ("AI_PROVIDER", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "MODEL_REASONING"):
        monkeypatch.setenv(name, "")

    settings = _settings()

    assert settings.ai_provider is None
    assert settings.resolved_ai_provider is None
    assert settings.ai_enabled is False
