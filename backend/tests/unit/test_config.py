"""
Unit tests for ill_bridge.config.
"""

from __future__ import annotations

import pytest
from ill_bridge.config import (
    LIBRIS_BASE_URL,
    Settings,
    check_for_unknown_env_vars,
    get_settings,
)
from pydantic import ValidationError


def build(**overrides: object) -> Settings:
    """Construct Settings with the required fields filled in."""
    defaults: dict[str, object] = {
        "libris_api_key": "test-key",
        "libris_sigel": "Hal",
        "_env_file": None,
    }
    return Settings(**{**defaults, **overrides})


class TestRequiredFields:
    # _env_file=None disables the .env file, so the test does not depend on any external configuration.
    def test_missing_api_key_names_the_field(self) -> None:
        with pytest.raises(ValidationError) as exc:
            # This code expects a validationError 
            Settings(libris_sigel="Hal", _env_file=None) 
        errors = exc.value.errors()
        assert errors[0]['type'] == 'missing'
        assert errors[0]['loc'] == ('ILL_LIBRIS_API_KEY',)

    # def test_missing_sigel_names_the_field(self) -> None:
    #     with pytest.raises(ValidationError) as exc:
    #         # This code expects a validationError 
    #         Settings(libris_api_key="k", _env_file=None) 
    #     assert "libris_sigel" in str(exc.value)

    # def test_module_imports_without_any_environment(self) -> None:
    #     """Importing must never require configuration.

    #     Regression guard: an earlier version instantiated Settings at module
    #     scope, so `import ill_bridge.config` raised KeyError and the package
    #     could not be imported by tests or tooling.
    #     """
    #     import importlib

    #     module = importlib.import_module("ill_bridge.config")
    #     assert hasattr(module, "get_settings")


# class TestSecretHandling:
#     def test_key_is_masked_in_repr(self) -> None:
#         settings = build(libris_api_key="super-secret-value")
#         assert "super-secret-value" not in repr(settings)
#         assert "super-secret-value" not in str(settings.libris_api_key)

#     def test_key_readable_only_via_explicit_call(self) -> None:
#         settings = build(libris_api_key="super-secret-value")
#         assert settings.libris_api_key.get_secret_value() == "super-secret-value"


# class TestSecretspecAliases:
#     def test_password_alias_supplies_the_api_key(
#         self, monkeypatch: pytest.MonkeyPatch
#     ) -> None:
#         monkeypatch.setenv("HALMSTAD_LIBRIS_PASSWORD", "aliased-key")
#         monkeypatch.setenv("HALMSTAD_LIBRIS_SIGEL", "Hal")
#         monkeypatch.setenv("HALMSTAD_LIBRIS_USERNAME", "Hal")
#         settings = Settings(_env_file=None)  # type: ignore[call-arg]
#         assert settings.libris_api_key.get_secret_value() == "aliased-key"

#     def test_username_alias_supplies_the_sigel(
#         self, monkeypatch: pytest.MonkeyPatch
#     ) -> None:
#         monkeypatch.setenv("HALMSTAD_LIBRIS_PASSWORD", "k")
#         monkeypatch.setenv("HALMSTAD_LIBRIS_USERNAME", "Bthg")
#         settings = Settings(_env_file=None)  # type: ignore[call-arg]
#         assert settings.libris_sigel == "Bthg"


# class TestSigelNormalisation:
#     @pytest.mark.parametrize("raw", [" Hal", "Hal ", "  Hal  ", "\tHal\n"])
#     def test_surrounding_whitespace_is_stripped(self, raw: str) -> None:
#         """Live user_id and sigel values arrive with stray whitespace.

#         41 of 1620 captured user_id values had it, and it collapsed 521
#         apparently distinct values to 516. The same hazard applies to a sigel
#         used as a path segment and an allowlist key.
#         """
#         assert build(libris_sigel=raw).libris_sigel == "Hal"


# class TestSigelAllowlist:
#     def test_defaults_to_the_configured_sigel(self) -> None:
#         assert build().libris_allowed_sigels == ["Hal"]

#     def test_configured_sigel_must_be_in_an_explicit_allowlist(self) -> None:
#         with pytest.raises(ValidationError, match="not in"):
#             build(libris_sigel="Hal", libris_allowed_sigels=["Bthg"])

#     def test_multi_sigel_tenant(self) -> None:
#         settings = build(libris_sigel="Bthg", libris_allowed_sigels=["Bthg", "Bthd"])
#         assert settings.is_sigel_allowed("Bthd")

#     def test_foreign_sigel_is_rejected(self) -> None:
#         """The API key is organisation-scoped, so the credential does not
#         isolate tenants. This check is the only thing that does."""
#         assert not build().is_sigel_allowed("Bthg")

#     def test_guard_tolerates_untrimmed_input(self) -> None:
#         assert build().is_sigel_allowed("  Hal  ")

#     def test_allowlist_entries_are_trimmed(self) -> None:
#         settings = build(libris_allowed_sigels=[" Hal ", "Bthg "])
#         assert settings.libris_allowed_sigels == ["Hal", "Bthg"]


# class TestEnvironmentGuards:
#     def test_mock_auth_allowed_locally(self) -> None:
#         assert build(environment="local", auth_mode="mock").auth_mode == "mock"

#     @pytest.mark.parametrize("environment", ["test", "staging", "production"])
#     def test_mock_auth_forbidden_outside_local(self, environment: str) -> None:
#         with pytest.raises(ValidationError, match="mock"):
#             build(
#                 environment=environment,
#                 auth_mode="mock",
#                 database_url="postgresql://x",
#                 redis_url="redis://x",
#             )

#     @pytest.mark.parametrize("value", ["Local", "LOCAL", "prod", "production "])
#     def test_unrecognised_environment_is_rejected(self, value: str) -> None:
#         """A free-form string here previously defeated the mock-auth guard:
#         ILL_ENVIRONMENT='Local' is not equal to 'local', so the check passed
#         while the deployment was not in fact local."""
#         with pytest.raises(ValidationError):
#             build(environment=value)

#     @pytest.mark.parametrize("environment", ["staging", "production"])
#     def test_database_and_redis_required(self, environment: str) -> None:
#         with pytest.raises(ValidationError, match="ILL_DATABASE_URL"):
#             build(environment=environment, redis_url="redis://x")

#         with pytest.raises(ValidationError, match="ILL_REDIS_URL"):
#             build(environment=environment, database_url="postgresql://x")

#     def test_plaintext_base_url_rejected_in_production(self) -> None:
#         with pytest.raises(ValidationError, match="https"):
#             build(
#                 environment="production",
#                 database_url="postgresql://x",
#                 redis_url="redis://x",
#                 libris_base_url="http://iller.libris.kb.se/librisfjarrlan/api",
#             )

#     def test_production_accepts_a_complete_configuration(self) -> None:
#         settings = build(
#             environment="production",
#             database_url="postgresql://x",
#             redis_url="redis://x",
#         )
#         assert settings.environment == "production"


# class TestSafeDefaults:
#     def test_writes_are_disabled(self) -> None:
#         """Libris has no undo. Writes must be opted into explicitly."""
#         assert build().libris_writes_enabled is False

#     def test_environment_defaults_to_local(self) -> None:
#         """An unconfigured deployment must not resemble production."""
#         assert build().environment == "local"

#     def test_base_url_points_at_the_documented_endpoint(self) -> None:
#         assert build().libris_base_url == LIBRIS_BASE_URL
#         assert build().libris_base_url.startswith("https://")

#     def test_poll_interval_default(self) -> None:
#         assert build().libris_poll_interval_seconds == 60

#     @pytest.mark.parametrize("seconds", [0, 1, 9, -5])
#     def test_poll_interval_floor_enforced(self, seconds: int) -> None:
#         """No documented Libris rate limit exists, so absence of a limit is
#         treated as unknown rather than unlimited."""
#         with pytest.raises(ValidationError):
#             build(libris_poll_interval_seconds=seconds)


# class TestPrecedence:
#     def test_keyword_argument_beats_environment(
#         self, monkeypatch: pytest.MonkeyPatch
#     ) -> None:
#         monkeypatch.setenv("ILL_LIBRIS_API_KEY", "k")
#         monkeypatch.setenv("ILL_LIBRIS_SIGEL", "FromEnv")
#         settings = Settings(libris_sigel="FromKwarg", _env_file=None)  # type: ignore[call-arg]
#         assert settings.libris_sigel == "FromKwarg"

#     def test_environment_beats_default(
#         self, monkeypatch: pytest.MonkeyPatch, minimal_env: dict[str, str]
#     ) -> None:
#         monkeypatch.setenv("ILL_LIBRIS_POLL_INTERVAL_SECONDS", "300")
#         assert Settings(_env_file=None).libris_poll_interval_seconds == 300  # type: ignore[call-arg]

#     def test_construction_by_field_name_is_supported(self) -> None:
#         """Regression guard: declaring validation_alias makes pydantic reject
#         the field name unless populate_by_name is set, which broke every test
#         that builds Settings directly."""
#         assert build(libris_sigel="Hal").libris_sigel == "Hal"


# class TestUnknownEnvVars:
#     def test_recognised_variables_are_not_flagged(
#         self, minimal_env: dict[str, str]
#     ) -> None:
#         assert check_for_unknown_env_vars() == []

#     def test_typo_is_flagged(
#         self, monkeypatch: pytest.MonkeyPatch, minimal_env: dict[str, str]
#     ) -> None:
#         monkeypatch.setenv("ILL_LIBRIS_POLL_INTERVAL_SECOND", "300")  # missing S
#         assert "ILL_LIBRIS_POLL_INTERVAL_SECOND" in check_for_unknown_env_vars()

#     def test_strict_mode_raises(
#         self, monkeypatch: pytest.MonkeyPatch, minimal_env: dict[str, str]
#     ) -> None:
#         monkeypatch.setenv("ILL_NOT_A_REAL_SETTING", "x")
#         with pytest.raises(ValueError, match="ILL_NOT_A_REAL_SETTING"):
#             get_settings(strict_env=True)


# class TestGetSettings:
#     def test_result_is_cached(self, minimal_env: dict[str, str]) -> None:
#         assert get_settings() is get_settings()

#     def test_cache_clear_picks_up_changes(
#         self, monkeypatch: pytest.MonkeyPatch, minimal_env: dict[str, str]
#     ) -> None:
#         assert get_settings().libris_sigel == "Hal"
#         monkeypatch.setenv("ILL_LIBRIS_SIGEL", "Bthg")
#         assert get_settings().libris_sigel == "Hal", "cached value should persist"
#         get_settings.cache_clear()
#         assert get_settings().libris_sigel == "Bthg"
