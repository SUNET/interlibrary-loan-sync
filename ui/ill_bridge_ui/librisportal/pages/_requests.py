"""Shared renderer for the two loan-direction pages.

``Utgående lån`` (lending) and ``Inkommande lån`` (borrowing) are the same
screen pointed at different Libris views, so they share one implementation
parameterised by a list of :class:`ViewTab`. Keeping them together means a fix
to filtering or the empty state lands in both directions at once.

A note on direction, because the endpoint names actively mislead: direction
follows the *payload*, not the URL. ``/incoming`` and ``/recent`` are LENDING
views (another library is asking us), while ``/inbox`` and ``/may_reserve``
are BORROWING views (we are asking someone else). See ``clients/libris.py``.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from nicegui import ui

from ill_bridge_ui.librisportal.deps import client
from ill_bridge_ui.librisportal.nav_config import LIBRIS_BRAND, LIBRIS_NAV
from ill_bridge_ui.shared import libris_records as lr
from ill_bridge_ui.shared.components import card, empty_state, metric, metric_grid, request_table
from ill_bridge_ui.shared.i18n import t
from ill_bridge_ui.shared.layout import page_header, page_shell


@dataclass(frozen=True)
class ViewTab:
    """One tab on a loan-direction page.

    Attributes:
        key: the Libris view name (``incoming``, ``inbox``, ...).
        label_key: i18n key for the tab label.
        media_type: optional upstream filter, ``"loan"`` or ``"copy"``.
    """

    key: str
    label_key: str
    media_type: str | None = None


def _columns() -> list[dict[str, Any]]:
    return [
        {"name": "title",      "label": t("req.col.item"),    "field": "title"},
        {"name": "library",    "label": t("req.col.library"), "field": "library"},
        {"name": "media_type", "label": t("req.col.media"),   "field": "media_type"},
        {"name": "status",     "label": t("req.col.status"),  "field": "status"},
        {"name": "updated",    "label": t("req.col.updated"), "field": "updated"},
        {"name": "lf_number",  "label": t("req.col.lf"),      "field": "lf_number"},
    ]


async def _load(tabs: tuple[ViewTab, ...]) -> dict[str, list[dict[str, Any]]]:
    """Fetch every tab's view concurrently.

    One failing view must not blank the whole page, so each result is resolved
    independently and failures degrade to an empty list with a single toast.
    """
    api = client()
    results = await asyncio.gather(
        *(api.view(tab.key, media_type=tab.media_type) for tab in tabs),
        return_exceptions=True,
    )
    data: dict[str, list[dict[str, Any]]] = {}
    failed = False
    for tab, result in zip(tabs, results):
        if isinstance(result, BaseException):
            failed = True
            data[tab.key] = []
        else:
            data[tab.key] = result
    if failed:
        ui.notify(t("toast.libris_error"), color="negative")
    return data


def _render_tab_body(rows: list[dict[str, Any]]) -> None:
    """Filter bar + table for a single tab, with client-side search.

    Libris has no pagination and no server-side text search — a view returns
    its full set — so filtering here is a plain in-memory pass over rows we
    already hold, not a hidden extra round trip.
    """
    state = {"query": "", "status": None}
    statuses = sorted({r["status"] for r in rows if r["status"] != "—"})

    def _matches(row: dict[str, Any]) -> bool:
        if state["status"] and row["status"] != state["status"]:
            return False
        q = state["query"].strip().lower()
        if not q:
            return True
        return any(
            q in str(row.get(field, "")).lower()
            for field in ("title", "subtitle", "library", "library_code", "lf_number")
        )

    def refresh() -> None:
        container.clear()
        visible = [r for r in rows if _matches(r)]
        with container:
            if not visible:
                empty_state(t("empty") if not rows else t("req.no_match"))
            else:
                request_table(_columns(), visible)

    with ui.row().classes("w-full items-center gap-3 px-5 py-3 filter-bar"):
        ui.input(placeholder=t("req.search")) \
            .props("outlined dense clearable") \
            .classes("flex-1 min-w-[220px]") \
            .on_value_change(lambda e: (state.update(query=e.value or ""), refresh()))
        ui.select(
            options={None: t("req.filter.all_statuses"), **{s: s for s in statuses}},
            value=None,
        ).props("outlined dense").classes("w-52") \
            .on_value_change(lambda e: (state.update(status=e.value), refresh()))

    container = ui.column().classes("w-full gap-0")
    refresh()


async def render_requests_page(
    *,
    active: str,
    eyebrow_key: str,
    title_key: str,
    description_key: str,
    tabs: tuple[ViewTab, ...],
) -> None:
    """Render a full loan-direction page."""
    with page_shell(LIBRIS_NAV, active=active, brand=LIBRIS_BRAND):
        page_header(eyebrow_key, title_key, description_key)

        raw = await _load(tabs)
        our_sigel = client().sigel
        rows_by_tab = {tab.key: lr.to_rows(raw[tab.key], our_sigel) for tab in tabs}
        total = sum(len(v) for v in raw.values())
        actionable = sum(lr.count_actionable(v) for v in raw.values())

        # KPIs are counts we can actually derive from the API. Response-time
        # medians and "new today" deltas would need history Libris does not
        # expose, so they are deliberately absent rather than faked.
        # Per-tab counts are not repeated here — the tab labels already carry
        # them, and six tiles wrapped onto an ugly second row.
        all_records = [r for records in raw.values() for r in records]
        loans = sum(1 for r in all_records if r.get("media_type_code") == "1")
        copies = sum(1 for r in all_records if r.get("media_type_code") == "2")
        with metric_grid(4):
            metric(t("req.metric.total"), total)
            metric(
                t("req.metric.actionable"), actionable,
                meta=t("req.metric.actionable_meta"),
                meta_kind="warning" if actionable else "success",
            )
            metric(t("req.metric.loans"), loans)
            metric(t("req.metric.copies"), copies)

        with ui.tabs().classes("w-full ill-tabs").props("align=left no-caps") as tab_bar:
            tab_elements = {
                tab.key: ui.tab(tab.key, label=f"{t(tab.label_key)} ({len(raw[tab.key])})")
                for tab in tabs
            }

        with ui.tab_panels(tab_bar, value=tab_elements[tabs[0].key]).classes("w-full bg-transparent"):
            for tab in tabs:
                with ui.tab_panel(tab_elements[tab.key]).classes("p-0"):
                    with card():
                        _render_tab_body(rows_by_tab[tab.key])
