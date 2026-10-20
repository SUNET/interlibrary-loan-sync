"""Tiny i18n helpers.

Language is stored in NiceGUI's per-user cookie storage (``app.storage.user``)
so each browser session keeps its own choice without a login.

Import :func:`t` and call it at *render* time — not at module import — so the
active language reflects the request that's rendering the page.
"""
from __future__ import annotations

from typing import Any

from nicegui import app as nicegui_app

from ill_bridge_ui.config import get_settings
from ill_bridge_ui.shared.i18n.strings import STRINGS, SUPPORTED_LANGS

_STORAGE_KEY = "lang"


def get_lang() -> str:
    """Current language for the active user, defaulting to settings.default_lang."""
    default = get_settings().default_lang
    try:
        # app.storage.user requires an active request context. Fall back to
        # the settings default outside of one (e.g. background tasks).
        lang = nicegui_app.storage.user.get(_STORAGE_KEY, default)
    except Exception:
        lang = default
    return lang if lang in SUPPORTED_LANGS else default


def set_lang(lang: str) -> None:
    """Persist a language choice in the user's storage."""
    if lang not in SUPPORTED_LANGS:
        return
    try:
        nicegui_app.storage.user[_STORAGE_KEY] = lang
    except Exception:
        pass


def t(key: str, /, **fmt: Any) -> str:
    """Translate ``key`` for the active language.

    Falls back to Swedish, then to the raw key. ``fmt`` values are applied
    via :meth:`str.format` if the string contains ``{name}`` placeholders.
    """
    lang = get_lang()
    text = STRINGS.get(lang, {}).get(key) or STRINGS["sv"].get(key) or key
    return text.format(**fmt) if fmt else text
