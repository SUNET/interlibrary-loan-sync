"""Queues page — depth by (queue, status) + oldest waiting per queue.

The backend returns two independent aggregations
(``{"depth": [...], "oldest_waiting": [...]}``); we render them as two
tables rather than pivoting into one, because:

* The status set is open (Procrastinate adds ``cancelled``/``aborted``/
  ``succeeded`` etc.), so a fixed pivot would silently drop columns.
* ``oldest_seconds`` only exists for queues with ``todo`` rows — merging
  would produce misleading NULLs for busy-but-drained queues.
"""
from __future__ import annotations

from nicegui import ui

from ill_bridge_ui.admin.deps import client
from ill_bridge_ui.admin.nav_config import ADMIN_NAV
from ill_bridge_ui.shared.clients import AdminApiError
from ill_bridge_ui.shared.components import card, empty_state, styled_table
from ill_bridge_ui.shared.i18n import t
from ill_bridge_ui.shared.layout import page_header, page_shell


def _depth_columns() -> list[dict]:
    return [
        {"name": "queue_name", "label": t("queues.col.name"),   "field": "queue_name", "align": "left"},
        {"name": "status",     "label": t("queues.col.status"), "field": "status",     "align": "left"},
        {"name": "count",      "label": t("queues.col.count"),  "field": "count",      "align": "right"},
    ]


def _oldest_columns() -> list[dict]:
    return [
        {"name": "queue_name",      "label": t("queues.col.name"),   "field": "queue_name",      "align": "left"},
        {"name": "oldest_seconds",  "label": t("queues.col.oldest"), "field": "oldest_seconds",  "align": "right"},
    ]


async def render() -> None:
    with page_shell(ADMIN_NAV, active="queues"):
        page_header("queues.eyebrow", "queues.title", "queues.description")
        try:
            data = await client().list_queues()
        except AdminApiError:
            ui.notify(t("toast.api_error"), color="negative")
            data = {"depth": [], "oldest_waiting": []}

        depth = data.get("depth", [])
        oldest = data.get("oldest_waiting", [])

        with card(t("queues.depth.title"), t("queues.depth.description")):
            # Composite row key: (queue_name, status) is unique per row.
            if depth:
                styled_table(
                    _depth_columns(),
                    [{**r, "_key": f"{r.get('queue_name')}::{r.get('status')}"} for r in depth],
                    row_key="_key",
                )
            else:
                empty_state(t("empty"))
        with card(t("queues.oldest.title"), t("queues.oldest.description")):
            if oldest:
                styled_table(_oldest_columns(), oldest, row_key="queue_name",
                             status_column=None)
            else:
                empty_state(t("empty"))
