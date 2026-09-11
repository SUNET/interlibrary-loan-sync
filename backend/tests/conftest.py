
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from ill_bridge.config import get_settings

# Prefixes the settings model recognises, including the secretspec aliases.
MANAGED_PREFIXES = ("ILL_", "HALMSTAD_", "MDE_", "MDV_")


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove inherited configuration and clear the settings cache.

    Autouse: auto-detect and apply to all tests, so that tests don't accidentally inherit settings from the environment.
    """
    for name in list(os.environ):
        if name.startswith(MANAGED_PREFIXES):
            monkeypatch.delenv(name, raising=False)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def minimal_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """The two required variables without which Settings cannot be built."""
    values = {"ILL_LIBRIS_API_KEY": "test-key", "ILL_LIBRIS_SIGEL": "Hal"}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values
