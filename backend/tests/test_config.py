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
