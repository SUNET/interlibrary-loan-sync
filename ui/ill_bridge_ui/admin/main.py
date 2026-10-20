"""Admin portal entry point.

Run with:
    python -m ill_bridge_ui.admin.main
    ill-admin-ui                      # via console script

Environment (ILL_UI_*):
    ILL_UI_ADMIN_API_BASE   default http://backend:8000/api/v1
    ILL_UI_HOST             default 0.0.0.0
    ILL_UI_PORT             default 8080
    ILL_UI_DEFAULT_LANG     default sv
    ILL_UI_ENVIRONMENT      default local
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from nicegui import app as nicegui_app, ui

from ill_bridge_ui.admin import deps
from ill_bridge_ui.admin.routes import register_pages
from ill_bridge_ui.config import get_settings
from ill_bridge_ui.shared.clients import AdminApiClient

logger = logging.getLogger(__name__)

# Portal-owned assets — not shared with librisportal.
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_CSS_PATH = _ASSETS_DIR / "css" / "global.css"


def _asset_fingerprint(path: Path) -> str:
    """Short content hash used to bust the browser cache on CSS changes.

    Without this, ``add_static_files`` serves the stylesheet with
    ``max-age=3600``, so an edited ``global.css`` keeps rendering from cache for
    up to an hour — the page then mixes new markup with old rules and the
    layout silently falls apart (unstyled nav links stop being flex rows, etc.).
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except OSError:  # pragma: no cover - asset missing is a packaging error
        logger.warning("asset missing, cannot fingerprint: %s", path)
        return "dev"


def _configure_assets() -> None:
    """Serve /assets/* from the packaged ``assets/`` directory and inject CSS.

    ``shared=True`` on add_head_html is required in NiceGUI 3.x when called
    at module scope — it emits the link tag on every page rather than only
    the currently rendering one.
    """
    settings = get_settings()
    # Long cache in production (URLs are fingerprinted, so it is safe); no cache
    # locally so a plain reload always picks up stylesheet edits.
    max_age = 3600 if settings.environment == "production" else 0
    nicegui_app.add_static_files("/assets", str(_ASSETS_DIR), max_cache_age=max_age)
    ui.add_head_html(
        f'<link rel="stylesheet" href="/assets/css/global.css?v={_asset_fingerprint(_CSS_PATH)}">',
        shared=True,
    )


def _wire_client() -> None:
    """Create the singleton :class:`AdminApiClient` and close it on shutdown."""
    settings = get_settings()
    client = AdminApiClient(settings.admin_api_base)
    deps.bootstrap(client)

    @nicegui_app.on_shutdown
    async def _close() -> None:
        await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    _configure_assets()
    _wire_client()
    register_pages()

    # storage_secret is required for app.storage.user (holds the language choice).
    # In production this must come from a real secret — for now, a fixed value
    # keeps local dev friction low; document it in README.
    ui.run(
        host=settings.host,
        port=settings.port,
        title="ILL Bridge — Administration",
        reload=False,
        storage_secret="dev-secret-change-me",
    )


if __name__ == "__main__":
    main()
