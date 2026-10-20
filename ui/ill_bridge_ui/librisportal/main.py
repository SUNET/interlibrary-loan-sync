"""Librisportal entry point — the librarian-facing ILL interface.

Run with:
    python -m ill_bridge_ui.librisportal.main

Environment (ILL_UI_*):
    ILL_UI_LIBRIS_BASE_URL  default http://localhost:9000/librisfjarrlan/api
    ILL_UI_LIBRIS_API_KEY   default fake-key
    ILL_UI_LIBRIS_SIGEL     default Hal
    ILL_UI_LIBRIS_GENERATE  default 0      (fake provider only)
    ILL_UI_HOST             default 0.0.0.0
    ILL_UI_PORT             default 8080
    ILL_UI_DEFAULT_LANG     default sv
    ILL_UI_ENVIRONMENT      default local

This portal reads from the Libris ILL API directly; only writes and enrichment
go through the ill-bridge backend. Point ``ILL_UI_LIBRIS_BASE_URL`` at the fake
provider locally and at iller.libris.kb.se in production — nothing else changes.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from nicegui import app as nicegui_app, ui

from ill_bridge_ui.config import get_settings
from ill_bridge_ui.librisportal import deps
from ill_bridge_ui.librisportal.routes import register_pages
from ill_bridge_ui.shared.clients import LibrisApiClient

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_CSS_PATH = _ASSETS_DIR / "css" / "global.css"


def _asset_fingerprint(path: Path) -> str:
    """Short content hash used to bust the browser cache on CSS changes.

    Without this, ``add_static_files`` serves the stylesheet with
    ``max-age=3600``, so an edited ``global.css`` keeps rendering from cache for
    up to an hour and the page mixes new markup with old rules.
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:  # pragma: no cover - asset missing is a packaging error
        logger.warning("asset missing, cannot fingerprint: %s", path)
        return "dev"


def _configure_assets() -> None:
    settings = get_settings()
    max_age = 3600 if settings.environment == "production" else 0
    nicegui_app.add_static_files("/assets", str(_ASSETS_DIR), max_cache_age=max_age)
    ui.add_head_html(
        f'<link rel="stylesheet" href="/assets/css/global.css?v={_asset_fingerprint(_CSS_PATH)}">',
        shared=True,
    )


def _wire_client() -> None:
    """Create the singleton :class:`LibrisApiClient` and close it on shutdown."""
    settings = get_settings()
    client = LibrisApiClient(
        settings.libris_base_url,
        settings.libris_api_key,
        settings.libris_sigel,
        generate=settings.libris_generate,
    )
    deps.bootstrap(client)
    logger.info(
        "librisportal -> %s (sigel=%s)", settings.libris_base_url, settings.libris_sigel,
    )

    @nicegui_app.on_shutdown
    async def _close() -> None:
        await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    _configure_assets()
    _wire_client()
    register_pages()

    ui.run(
        host=settings.host,
        port=settings.port,
        title="ILL Bridge — Fjärrlån",
        reload=False,
        storage_secret="dev-secret-change-me",
    )


if __name__ == "__main__":
    main()
