"""Jobs page — table with status filter + retry/cancel actions."""
from __future__ import annotations

from nicegui import ui

from ill_bridge_ui.admin.deps import client
from ill_bridge_ui.admin.nav_config import ADMIN_NAV
from ill_bridge_ui.shared.clients import AdminApiError
from ill_bridge_ui.shared.components import card, empty_state, styled_table
from ill_bridge_ui.shared.i18n import t
from ill_bridge_ui.shared.layout import page_header, page_shell

# Statuses from the backend's JOB_STATUSES; kept as literals here to avoid
# importing the backend package. Keep in sync manually — a single source of
# truth would require a shared schemas package.
_STATUSES = ("todo", "doing", "succeeded", "failed", "cancelled", "aborting", "aborted")


def _columns() -> list[dict]:
    return [
        {"name": "id",         "label": t("jobs.col.id"),        "field": "id",         "align": "left"},
        {"name": "task_name",  "label": t("jobs.col.task"),      "field": "task_name",  "align": "left"},
        {"name": "queue_name", "label": t("jobs.col.queue"),     "field": "queue_name", "align": "left"},
        {"name": "status",     "label": t("jobs.col.status"),    "field": "status",     "align": "left"},
        {"name": "attempts",   "label": t("jobs.col.attempts"),  "field": "attempts",   "align": "right"},
        {"name": "scheduled_at", "label": t("jobs.col.scheduled"), "field": "scheduled_at", "align": "left"},
        {"name": "actions",    "label": "",                      "field": "id",         "align": "right"},
    ]


async def render() -> None:
    api = client()

    with page_shell(ADMIN_NAV, active="jobs"):
        page_header("jobs.eyebrow", "jobs.title", "jobs.description")

        # Reactive filter model. The toolbar must be created before the table
        # container so it renders above it — NiceGUI appends in creation order.
        state = {"status": None}

        async def refresh() -> None:
            container.clear()
            try:
                rows = await api.list_jobs(status=state["status"], limit=50)
            except AdminApiError:
                ui.notify(t("toast.api_error"), color="negative")
                rows = []
            with container:
                if not rows:
                    empty_state(t("empty"))
                    return
                tbl = styled_table(_columns(), rows, row_key="id")
                tbl.add_slot("body-cell-id", """
                    <q-td :props="props">
                        <a :href="'/jobs/' + props.row.id" class="text-primary font-bold">
                            #{{ props.row.id }}
                        </a>
                    </q-td>
                """)
                # Row action slot — Quasar 'body-cell-<name>' scoped slot.
                tbl.add_slot("body-cell-actions", """
                    <q-td :props="props" class="text-right">
                        <q-btn flat dense size="sm" no-caps
                               :label="'""" + t("jobs.action.retry") + """'"
                               @click="$parent.$emit('retry', props.row.id)" />
                        <q-btn flat dense size="sm" no-caps color="negative"
                               :label="'""" + t("jobs.action.cancel") + """'"
                               @click="$parent.$emit('cancel', props.row.id)" />
                    </q-td>
                """)
                tbl.on("retry", lambda e: ui.timer(0, lambda: _retry(e.args), once=True))
                tbl.on("cancel", lambda e: ui.timer(0, lambda: _cancel(e.args), once=True))

        async def _retry(job_id: int) -> None:
            try:
                await api.retry_job(int(job_id))
                ui.notify(t("toast.retry_ok"), color="positive")
            except AdminApiError as exc:
                ui.notify(str(exc), color="negative")
            await refresh()

        async def _cancel(job_id: int) -> None:
            try:
                await api.cancel_job(int(job_id))
                ui.notify(t("toast.cancel_ok"), color="positive")
            except AdminApiError as exc:
                ui.notify(str(exc), color="negative")
            await refresh()

        with card(t("jobs.title"), t("jobs.description")):
            # Toolbar sits inside the card, under the header, like the mock.
            with ui.row().classes("w-full items-center gap-3 px-5 py-3 toolbar"):
                ui.select(
                    options={None: t("jobs.filter.all"), **{s: s for s in _STATUSES}},
                    value=None,
                    label=t("jobs.filter.status"),
                    on_change=lambda e: (state.update(status=e.value),
                                         ui.timer(0, refresh, once=True)),
                ).props("dense outlined").classes("w-48")
                ui.space()
                ui.button(t("action.refresh"), icon="refresh", on_click=refresh) \
                    .props("flat dense no-caps")

            container = ui.column().classes("w-full gap-0")
            await refresh()
