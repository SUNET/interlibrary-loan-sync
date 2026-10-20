"""Process-wide accessor for the Libris API client.

NiceGUI runs in a single process, so a module-global singleton is fine and
avoids threading :class:`LibrisApiClient` through every page function.

:func:`bootstrap` is called once by ``librisportal/main.py`` at startup;
:func:`client` is called by pages at render time.
"""
from __future__ import annotations

from ill_bridge_ui.shared.clients import LibrisApiClient

_client: LibrisApiClient | None = None


def bootstrap(instance: LibrisApiClient) -> None:
    global _client
    _client = instance


def client() -> LibrisApiClient:
    if _client is None:
        raise RuntimeError("LibrisApiClient not initialised — call bootstrap() first.")
    return _client
