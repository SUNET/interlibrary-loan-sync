"""Process-wide accessor for the admin API client.

NiceGUI runs in a single process, so a module-global singleton is fine
and avoids threading ``AdminApiClient`` through every page function.

:func:`bootstrap` is called once by ``admin/main.py`` at startup;
:func:`client` is called by pages at render time.
"""
from __future__ import annotations

from ill_bridge_ui.shared.clients import AdminApiClient

_client: AdminApiClient | None = None


def bootstrap(instance: AdminApiClient) -> None:
    global _client
    _client = instance


def client() -> AdminApiClient:
    if _client is None:
        raise RuntimeError("AdminApiClient not initialised — call bootstrap() first.")
    return _client
