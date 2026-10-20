"""The app shell — Quasar header + left drawer + main content slot.

Every page uses :func:`page_shell` as a context manager. The shell renders a
``ui.header`` (hamburger + brand + environment badge + last-refresh + language
switcher) and a ``ui.left_drawer`` (driven by a portal-specific list of
:class:`NavGroup`), then yields the main content area to the caller.

Why Quasar layout slots instead of a hand-rolled CSS grid: ``ui.header`` and
``ui.left_drawer`` live in the ``q-layout`` that NiceGUI already creates, so we
get full-width sticky positioning, the mobile overlay/backdrop behaviour and
the content offset for free. A custom ``<header>`` + ``display:grid`` shell
placed inside ``.nicegui-content`` fights that layout instead of using it — it
never spans the viewport and has no way to toggle the sidebar.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Iterator

from nicegui import ui

from ill_bridge_ui.config import get_settings
from ill_bridge_ui.shared.i18n import get_lang, set_lang, t
from ill_bridge_ui.shared.i18n.strings import SUPPORTED_LANGS
from ill_bridge_ui.shared.layout.nav import NavGroup

# Environments that should read as "healthy green" in the header badge.
_ENV_TONE = {
    "local": ("#edf7ee", "#2E7D32"),
    "staging": ("#fff4e8", "#ED6C02"),
    "production": ("#fdeeee", "#D32F2F"),
}


@dataclass(frozen=True)
class Brand:
    """Portal-specific header branding, resolved through i18n at render time."""

    subtitle_key: str
    tagline_key: str
    title_key: str = "brand.title"


# Each portal passes its own; defaults keep the admin portal's existing look.
ADMIN_BRAND = Brand("brand.subtitle", "brand.tagline")


def _render_header(drawer: ui.left_drawer, brand: Brand) -> None:
    settings = get_settings()

    with ui.header().classes("app-header items-center justify-between px-4 lg:px-5"):
        # --- left: hamburger + brand -------------------------------------
        with ui.row().classes("items-center gap-3 no-wrap"):
            ui.button(icon="menu", on_click=drawer.toggle) \
                .props("flat round dense").classes("nav-toggle")

            with ui.row().classes("items-center gap-3 no-wrap"):
                ui.label("ILL").classes("brand-mark")
                with ui.column().classes("gap-0"):
                    with ui.row().classes("items-center gap-1 no-wrap"):
                        ui.label(t(brand.title_key)).classes("font-bold text-base")
                        ui.label(f"· {t(brand.subtitle_key)}").classes("text-base light")
                    ui.label(t(brand.tagline_key)).classes("text-xs light")

        # --- right: env badge + last refresh + language -------------------
        with ui.row().classes("items-center gap-4 no-wrap"):
            bg, fg = _ENV_TONE.get(settings.environment, _ENV_TONE["local"])
            with ui.row().classes("items-center gap-2 px-3 py-1 rounded-full no-wrap") \
                    .style(f"background:{bg};color:{fg};"):
                ui.icon("circle").style("font-size:7px")
                ui.label(t(f"env.{settings.environment}").upper()).classes("text-xs font-bold")

            ui.label(
                t("header.last_refresh", time=datetime.now().strftime("%H:%M:%S"))
            ).classes("text-xs light gt-xs")

            _render_language_switcher()


def _render_language_switcher() -> None:
    def _on_change(e) -> None:
        set_lang(e.value)
        # Full reload so every t() call re-resolves. Cheap; the shell is light.
        ui.navigate.reload()

    ui.select(
        options=list(SUPPORTED_LANGS),
        value=get_lang(),
        on_change=_on_change,
    ).props("dense borderless").classes("lang-switch")


def _render_drawer(groups: Iterable[NavGroup], active: str) -> ui.left_drawer:
    drawer = ui.left_drawer(value=True, bordered=True) \
        .props("width=250 breakpoint=850").classes("app-drawer bg-white p-0")

    with drawer:
        for group in groups:
            ui.label(t(group.label_key)).classes("sidebar-label")
            for item in group.items:
                cls = "nav-item" + (" active" if item.key == active else "")
                with ui.link(target=item.route).classes(cls):
                    ui.icon(item.icon).classes("nav-icon")
                    ui.label(t(item.label_key)).classes("nav-text")
                    if item.badge:
                        ui.badge(item.badge).props("rounded").classes("nav-badge")
    return drawer


@contextmanager
def page_shell(nav_groups: Iterable[NavGroup], active: str,
               brand: Brand = ADMIN_BRAND) -> Iterator[ui.element]:
    """Render header + drawer, yielding the main content column.

    Args:
        nav_groups: portal-specific sidebar structure.
        active: ``NavItem.key`` to highlight.
        brand: header branding for this portal.
    """
    # The drawer must exist before the header so the hamburger can toggle it.
    drawer = _render_drawer(nav_groups, active)
    _render_header(drawer, brand)

    with ui.column().classes("page-content w-full max-w-[1600px] mx-auto p-6 gap-5") as main:
        yield main


def page_header(eyebrow_key: str, title_key: str, description_key: str) -> None:
    """Standard title block above the main content."""
    with ui.row().classes("w-full items-end justify-between gap-4"):
        with ui.column().classes("gap-0"):
            ui.label(t(eyebrow_key)).classes("eyebrow")
            ui.label(t(title_key)).classes("page-title")
            ui.label(t(description_key)).classes("text-sm muted mt-1")
