"""Runtime settings for the UI processes.

Uses pydantic-settings, same pattern as the backend. Each portal instantiates
:class:`UiSettings` at startup; env vars are shared but each portal can pick
its own ILL_UI_PORT / ILL_UI_HOST via distinct env in docker-compose.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UiSettings(BaseSettings):
    """Environment-driven configuration for a UI portal."""

    model_config = SettingsConfigDict(
        env_prefix="ILL_UI_",
        env_file=".env",
        extra="ignore",
    )

    # Where to reach the backend Admin API. Includes the /api/v1 prefix so
    # the client can concatenate paths like /admin/jobs without special-casing.
    admin_api_base: str = Field(
        default="http://localhost:8000/api/v1",
        description="Base URL for the ill-bridge Admin REST API.",
    )

    # HTTP surface for this UI process.
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080)

    # i18n
    default_lang: str = Field(default="sv", description="Fallback UI language (sv|en).")

    # --- Libris ILL API (librisportal) ------------------------------------
    # The librisportal talks to Libris directly for reads. Point this at the
    # fake provider locally and at iller.libris.kb.se in production:
    #   fake: http://localhost:9000/librisfjarrlan/api
    #   prod: https://iller.libris.kb.se/librisfjarrlan/api
    libris_base_url: str = Field(
        default="http://localhost:9000/librisfjarrlan/api",
        description="Base URL for the Libris ILL API, including /librisfjarrlan/api.",
    )
    # Libris authenticates with an `api-key` HTTP header — not a bearer token
    # and not basic auth. The fake provider only checks that it is non-empty.
    libris_api_key: str = Field(
        default="fake-key",
        description="Value sent in the `api-key` header on every Libris call.",
    )
    # Our own library's sigel. Every Libris path is scoped to it, and an unknown
    # sigel returns `count: 0` rather than a 404 — so a typo here looks exactly
    # like a quiet week. "Hal" is the sigel the bundled fixtures were captured for.
    libris_sigel: str = Field(
        default="Hal",
        description="Our library code (sigel); scopes every Libris request.",
    )
    # Simulator-only: ask the fake provider to synthesise N records for views
    # that have no fixture. Must be 0 against the real API, which rejects it.
    libris_generate: int = Field(
        default=0,
        ge=0,
        description="Fake-provider record generation count. Keep 0 in production.",
    )

    # Cosmetic
    environment: str = Field(default="local", description="Shown in the header pill.")


@lru_cache(maxsize=1)
def get_settings() -> UiSettings:
    """Cached accessor — settings are immutable per process."""
    return UiSettings()
