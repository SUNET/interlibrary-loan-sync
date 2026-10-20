"""Job details and Procrastinate lifecycle history."""
from __future__ import annotations

import json

from nicegui import ui

from ill_bridge_ui.admin.deps import client
from ill_bridge_ui.admin.nav_config import ADMIN_NAV
from ill_bridge_ui.shared.clients import AdminApiError
from ill_bridge_ui.shared.components import card, empty_state, status_pill, styled_table
from ill_bridge_ui.shared.i18n import t
from ill_bridge_ui.shared.layout import page_header, page_shell


def _field(label: str, value: object) -> None:
    with ui.column().classes("gap-0 min-w-0"):
        ui.label(label).classes("text-xs muted")
        ui.label(str(value) if value is not None else "-").classes("break-all")


async def render(job_id: int) -> None:
    api = client()
    with page_shell(ADMIN_NAV, active="jobs"):
        page_header("jobs.eyebrow", "job.title", "job.description")
        ui.link(t("job.back"), "/jobs").classes("text-primary")
        content = ui.column().classes("w-full gap-5")

        async def refresh() -> None:
            try:
                job = await api.get_job(job_id)
            except AdminApiError as exc:
                content.clear()
                with content:
                    empty_state(t("job.not_found") if exc.status_code == 404 else t("toast.api_error"))
                return

            try:
                events = await api.get_job_events(job_id)
                events_error = False
            except AdminApiError:
                events = []
                events_error = True

            content.clear()
            with content:
                def refresh_button() -> None:
                    ui.button(t("action.refresh"), icon="refresh", on_click=refresh).props(
                        "flat dense no-caps"
                    )

                with card(f"#{job_id} - {job['task_name']}", right=refresh_button):
                    with ui.column().classes("w-full p-5 gap-4"):
                        status_pill(str(job["status"]), {
                            "doing": "running", "succeeded": "success", "failed": "error",
                            "aborting": "warning", "aborted": "warning",
                        }.get(job["status"], "neutral"))
                        with ui.grid().classes("w-full gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"):
                            for key, label in (
                                ("queue_name", "jobs.col.queue"),
                                ("attempts", "jobs.col.attempts"),
                                ("scheduled_at", "jobs.col.scheduled"),
                                ("worker_id", "job.worker"),
                                ("priority", "job.priority"),
                                ("lock", "job.lock"),
                                ("queueing_lock", "job.queueing_lock"),
                                ("abort_requested", "job.abort_requested"),
                            ):
                                value = job.get(key)
                                if key == "scheduled_at" and value is None:
                                    value = t("job.run_now")
                                _field(t(label), value)

                with card(t("job.args.title"), t("job.args.description"), padded=True):
                    with ui.element("div").classes("w-full overflow-auto"):
                        ui.code(
                            json.dumps(job.get("args") or {}, ensure_ascii=False, indent=2),
                            language="json",
                        )

                with card(t("job.events.title"), t("job.events.description")):
                    if events_error:
                        empty_state(t("toast.api_error"))
                    elif not events:
                        empty_state(t("job.events.empty"))
                    else:
                        styled_table([
                            {"name": "at", "label": t("job.events.at"), "field": "at"},
                            {"name": "type", "label": t("job.events.type"), "field": "type"},
                        ], events, status_column=None)
                with card(t("job.logs.title"), padded=True):
                    ui.label(t("job.logs.unavailable")).classes("muted text-sm")

        await refresh()
