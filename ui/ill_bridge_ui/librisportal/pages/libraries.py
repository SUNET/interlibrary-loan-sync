"""Bibliotek — the Libris library directory.

Shows the libraries we can transact with, plus our own entry. Contact details
matter here: when a request stalls, the next step is usually an email or a
phone call to the other library's ILL desk.
"""
from __future__ import annotations

import asyncio
from typing import Any

from nicegui import ui

from ill_bridge_ui.librisportal.deps import client
from ill_bridge_ui.librisportal.nav_config import LIBRIS_BRAND, LIBRIS_NAV
from ill_bridge_ui.shared.components import (
    card, empty_state, metric, metric_grid, status_pill, styled_table,
)
from ill_bridge_ui.shared.i18n import t
from ill_bridge_ui.shared.layout import page_header, page_shell


def _columns() -> list[dict[str, Any]]:
    return [
        {"name": "library_code", "label": t("lib.col.sigel"),   "field": "library_code"},
        {"name": "name",         "label": t("lib.col.name"),    "field": "name"},
        {"name": "city",         "label": t("lib.col.city"),    "field": "city"},
        {"name": "email",        "label": t("lib.col.contact"), "field": "email"},
        {"name": "status",       "label": t("lib.col.status"),  "field": "status"},
    ]


def _to_row(record: dict[str, Any]) -> dict[str, Any]:
    """Flatten a directory entry.

    ``closed`` is the one operational flag that changes what a librarian should
    do: a closed library will not answer, so it is surfaced as the row status
    rather than buried in the detail fields.
    """
    closed = bool(record.get("closed"))
    reason = record.get("closed_reason") or ""
    return {
        "library_code": record.get("library_code") or "—",
        "name": record.get("name") or "—",
        "city": record.get("city") or "—",
        # The directory has several address slots; the general ILL mailbox is
        # the one a librarian actually writes to.
        "email": record.get("email_general") or record.get("email") or "—",
        "status": f"{t('lib.closed')} · {reason}".strip(" ·") if closed else t("lib.open"),
        "status_tone": "warning" if closed else "success",
    }


async def _load() -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    api = client()
    directory, ours = await asyncio.gather(
        api.libraries("all_libraries"),
        api.our_library(),
        return_exceptions=True,
    )
    if isinstance(directory, BaseException):
        ui.notify(t("toast.libris_error"), color="negative")
        directory = []
    if isinstance(ours, BaseException):
        ours = None
    return directory, ours


async def render() -> None:
    with page_shell(LIBRIS_NAV, active="libraries", brand=LIBRIS_BRAND):
        page_header("lib.eyebrow", "lib.title", "lib.description")

        directory, ours = await _load()
        rows = [_to_row(r) for r in directory]
        closed = sum(1 for r in rows if r["status_tone"] == "warning")

        with metric_grid(4):
            metric(t("lib.metric.total"), len(rows))
            metric(t("lib.metric.open"), len(rows) - closed,
                   meta=t("lib.metric.open_meta"), meta_kind="success")
            metric(t("lib.metric.closed"), closed,
                   meta=t("lib.metric.closed_meta"),
                   meta_kind="warning" if closed else "success")
            metric(t("lib.metric.sigel"), client().sigel)

        # Our own entry first — a librarian checking "are we reachable?" should
        # not have to search the directory for their own library.
        if ours:
            with card(t("lib.ours.title"), t("lib.ours.description")):
                _render_details(ours)

        with card(t("lib.directory.title"), t("lib.directory.description")):
            _render_directory(rows)


def _render_details(record: dict[str, Any]) -> None:
    """Key contact fields for our own library."""
    fields = (
        ("lib.field.name", record.get("name")),
        ("lib.field.contact_person", record.get("contact_person")),
        ("lib.field.email", record.get("email_general")),
        ("lib.field.requests", record.get("email_requests") or "—"),
        ("lib.field.city", record.get("city")),
    )
    with ui.grid().classes("w-full gap-4 p-5 grid-cols-1 md:grid-cols-3"):
        for key, value in fields:
            with ui.column().classes("gap-0"):
                ui.label(t(key)).classes("metric-label")
                ui.label(str(value or "—")).classes("text-sm")
    if record.get("closed"):
        with ui.row().classes("items-center gap-2 px-5 pb-5"):
            status_pill(
                f"{t('lib.closed')} {record.get('closed_from') or ''}"
                f"–{record.get('closed_until') or ''}".strip(),
                "warning",
            )
            ui.label(record.get("closed_reason") or "").classes("text-xs muted")


def _render_directory(rows: list[dict[str, Any]]) -> None:
    """Searchable directory table with client-side filtering."""
    state = {"query": ""}

    def refresh() -> None:
        container.clear()
        q = state["query"].strip().lower()
        visible = [
            r for r in rows
            if not q or any(
                q in str(r[f]).lower()
                for f in ("library_code", "name", "city", "email")
            )
        ]
        with container:
            if not visible:
                empty_state(t("empty") if not rows else t("req.no_match"))
            else:
                table = styled_table(_columns(), visible, row_key="library_code",
                                     status_column=None)
                table.add_slot("body-cell-status", """
                    <q-td :props="props">
                        <span class="status" :class="'status-' + props.row.status_tone">
                            {{ props.row.status }}
                        </span>
                    </q-td>
                """)

    with ui.row().classes("w-full items-center gap-3 px-5 py-3 filter-bar"):
        ui.input(placeholder=t("lib.search")) \
            .props("outlined dense clearable") \
            .classes("flex-1 min-w-[220px]") \
            .on_value_change(lambda e: (state.update(query=e.value or ""), refresh()))

    container = ui.column().classes("w-full gap-0")
    refresh()
