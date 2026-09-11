from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from ill_bridge import __version__

Environment = Literal["local", "test", "staging", "production"]
AuthMode = Literal["oidc", "mock"]


LIBRIS_BASE_URL = "https://iller.libris.kb.se/librisfjarrlan/api"


class Settings(BaseSettings):
    """Runtime configuration, validated once at startup."""

    # Precedence -> [Settings(...) keyword arguments, os.environ, .env file, field defaults]
    model_config = SettingsConfigDict(
        env_prefix="ILL_",
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,  # Make Settings(libris_sigel="Hal") = Settings(ILL_LIBRIS_SIGEL="Hal") = Settings(HALMSTAD_LIBRIS_USERNAME="Hal")
        extra="forbid",  # Forbid unknown fields in Settings(...) constructor extra = "forbid" | "allow" | "ignore"
    )

    # --- Libris provider -------------------------------------------------
    # SecretStr keeps the key out of repr(), tracebacks and log dumps.
    libris_api_key: SecretStr = Field(
        validation_alias=AliasChoices(
            "ILL_LIBRIS_API_KEY",
            "HALMSTAD_LIBRIS_PASSWORD",  # secretspec.toml name
        ),
    )
    libris_sigel: str = Field(
        validation_alias=AliasChoices(
            "ILL_LIBRIS_SIGEL",
            "HALMSTAD_LIBRIS_USERNAME",
        ),
    )
    libris_allowed_sigels: list[str] = Field(default_factory=list)
    libris_base_url: str = LIBRIS_BASE_URL
    libris_writes_enabled: bool = False  # Libris has no undo. Opt in explicitly.
    libris_poll_interval_seconds: int = Field(default=60, ge=10)

    # --- Ill-bridge ----------------------------------------------------
    api_title: str = "ILL Bridge"
    api_version: str = __version__
    api_root_path: str = ""
    cors_origins: list[str] = Field(default_factory=list)
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    database_url: str | None = None
    redis_url: str | None = None

    # --- Environment -----------------------------------------------------
    environment: Environment = "local"
    auth_mode: AuthMode = "oidc"
    log_level: str = "INFO"

    @field_validator("libris_sigel")
    @classmethod
    def _strip_sigel(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _check_consistency(self) -> Settings:
        if not self.libris_allowed_sigels:
            self.libris_allowed_sigels = [self.libris_sigel]

        cleaned = [s.strip() for s in self.libris_allowed_sigels if s.strip()]
        if self.libris_sigel not in cleaned:
            raise ValueError(
                f"libris_sigel {self.libris_sigel!r} is not in "
                f"libris_allowed_sigels {cleaned}"
            )
        self.libris_allowed_sigels = cleaned

        if self.auth_mode == "mock" and self.environment != "local":
            raise ValueError(
                f"auth_mode='mock' is forbidden outside local "
                f"(environment={self.environment!r})"
            )

        if self.environment in ("staging", "production"):
            missing = [
                name
                for name, value in (
                    ("ILL_DATABASE_URL", self.database_url),
                    ("ILL_REDIS_URL", self.redis_url),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"{', '.join(missing)} required when environment="
                    f"{self.environment!r}"
                )

            if not self.libris_base_url.startswith("https://"):
                raise ValueError(
                    "libris_base_url must use https outside local development"
                )

        # The API is served with allow_credentials=True, and browsers reject
        # a wildcard origin in that combination.
        self.cors_origins = [origin.strip() for origin in self.cors_origins if origin.strip()]
        if "*" in self.cors_origins:
            raise ValueError(
                'cors_origins cannot contain "*" because credentials are '
                "allowed; list explicit origins instead"
            )

        return self

    def is_sigel_allowed(self, sigel: str) -> bool:
        """Guard for any request that selects data by library code."""
        return sigel.strip() in self.libris_allowed_sigels


def _accepted_env_names() -> set[str]:
    """Every ILL_* variable name the Settings model will actually read [fields + aliases]."""
    prefix = Settings.model_config.get("env_prefix", "")
    names: set[str] = set()
    for field_name, field in Settings.model_fields.items():
        names.add(f"{prefix}{field_name}".upper())
        alias = field.validation_alias
        if isinstance(alias, AliasChoices):
            names.update(str(choice).upper() for choice in alias.choices)
        elif isinstance(alias, str):
            names.add(alias.upper())
    return names


def check_for_unknown_env_vars() -> list[str]:
    """
    Return ILL_* variables in the environment that nothing will read.
    Catch cases where env contains ILL_LIBRIS_API_KEI instead of ILL_LIBRIS_API_KEY
    """
    prefix = Settings.model_config.get("env_prefix", "")
    accepted = _accepted_env_names()
    return sorted(
        name
        for name in os.environ
        if name.startswith(prefix) and name.upper() not in accepted
    )


@lru_cache
def get_settings(*, strict_env: bool = True) -> Settings:
    """Return the validated settings, loaded once per process.

    Lazy so that importing this module never requires a populated
    environment. Use as a FastAPI dependency:

        @app.get("/health")
        def health(settings: Settings = Depends(get_settings)): ...

    Set ``strict_env=False`` to tolerate unrecognised ``ILL_*`` variables,
    for example when several services share one environment.
    """
    if strict_env:
        unknown = check_for_unknown_env_vars()
        if unknown:
            raise ValueError(
                f"unrecognised environment variables (typo?): {', '.join(unknown)}"
            )
    return Settings()
