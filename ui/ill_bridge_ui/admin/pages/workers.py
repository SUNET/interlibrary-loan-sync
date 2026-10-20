"""Workers page — heartbeats + current work."""
from __future__ import annotations

from nicegui import ui

from ill_bridge_ui.admin.deps import client
from ill_bridge_ui.admin.nav_config import ADMIN_NAV
from ill_bridge_ui.shared.clients import AdminApiError
from ill_bridge_ui.shared.components import card, empty_state, styled_table
from ill_bridge_ui.shared.i18n import t
from ill_bridge_ui.shared.layout import page_header, page_shell


def _columns() -> list[dict]:
    return [
        {"name": "id",             "label": t("workers.col.id"),        "field": "id",             "align": "left"},
        {"name": "last_heartbeat", "label": t("workers.col.heartbeat"), "field": "last_heartbeat", "align": "left"},
        {"name": "heartbeat_age_seconds", "label": t("workers.col.age"), "field": "heartbeat_age_seconds", "align": "right"},
        {"name": "doing_count",    "label": t("workers.col.doing"),     "field": "doing_count",    "align": "right"},
    ]


async def render() -> None:
    with page_shell(ADMIN_NAV, active="workers"):
        page_header("workers.eyebrow", "workers.title", "workers.description")
        try:
            rows = await client().list_workers()
        except AdminApiError:
            ui.notify(t("toast.api_error"), color="negative")
            rows = []
        with card(t("workers.title"), t("workers.description")):
            if rows:
                styled_table(_columns(), rows, row_key="id", status_column=None)
            else:
                empty_state(t("empty"))
