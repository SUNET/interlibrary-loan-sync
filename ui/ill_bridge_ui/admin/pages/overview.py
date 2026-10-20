"""Overview page — KPIs + running jobs + recent failures."""
from __future__ import annotations

import asyncio

from nicegui import ui

from ill_bridge_ui.admin.deps import client
from ill_bridge_ui.admin.nav_config import ADMIN_NAV
from ill_bridge_ui.shared.clients import AdminApiError
from ill_bridge_ui.shared.components import (
    card, empty_state, metric, metric_grid, status_pill,
)
from ill_bridge_ui.shared.i18n import t
from ill_bridge_ui.shared.layout import page_header, page_shell


_EMPTY_QUEUES: dict[str, list[dict]] = {"depth": [], "oldest_waiting": []}


async def _load() -> dict:
    """Fetch all overview data in parallel; return an empty-ish dict on error.

    A single API outage should not blank the page — the toast is enough to
    signal the state. Falling back to zeros keeps the layout stable.
    """
    api = client()
    try:
        running, queues, workers, failed = await asyncio.gather(
            api.list_running_jobs(),
            api.list_queues(),
            api.list_workers(),
            api.list_failed_jobs(limit=5),
        )
    except AdminApiError as exc:
        ui.notify(t("toast.api_error"), color="negative")
        return {
            "error": str(exc),
            "running": [],
            "queues": _EMPTY_QUEUES,
            "workers": [],
            "failed": [],
        }
    return {"running": running, "queues": queues, "workers": workers, "failed": failed}


def _queued_total(depth: list[dict]) -> int:
    """Sum of ``todo`` counts across all queues.

    ``depth`` is a list of ``{queue_name, status, count}`` — we intentionally
    only count ``todo`` here because ``doing`` is already surfaced via the
    running-jobs KPI and ``failed`` via the failed-jobs KPI.
    """
    return sum(int(r.get("count", 0)) for r in depth if r.get("status") == "todo")


def _oldest_seconds(oldest_waiting: list[dict]) -> int:
    """Largest ``oldest_seconds`` across queues, or 0 if none."""
    values = [int(r.get("oldest_seconds") or 0) for r in oldest_waiting]
    return max(values) if values else 0


async def render() -> None:
    with page_shell(ADMIN_NAV, active="overview"):
        page_header("overview.eyebrow", "overview.title", "overview.description")

        data = await _load()
        running = data["running"]
        queues = data["queues"]
        workers = data["workers"]
        failed = data["failed"]

        # KPIs
        depth = queues.get("depth", [])
        oldest_rows = queues.get("oldest_waiting", [])
        queued_total = _queued_total(depth)
        oldest = _oldest_seconds(oldest_rows)
        with metric_grid():
            metric(t("overview.metric.running"), len(running))
            metric(t("overview.metric.queued"), queued_total)
            metric(t("overview.metric.failed"), len(failed),
                   meta_kind="error" if failed else "success",
                   meta=(f"{len(failed)}") if failed else "0")
            metric(t("overview.metric.workers"), len(workers))
            metric(t("overview.metric.oldest"), f"{oldest}s" if oldest else "—")

        # Split: running jobs on the left, recent failures on the right.
        with ui.row().classes("w-full items-start gap-5 no-wrap max-lg:flex-wrap"):
            with ui.column().classes("flex-1 min-w-0 gap-5"):
                with card(t("overview.running.title"), t("overview.running.description")):
                    if not running:
                        empty_state(t("empty"))
                    for j in running:
                        with ui.element("div").classes("job-row"):
                            with ui.column().classes("gap-0 flex-1 min-w-0"):
                                ui.label(j.get("task_name", "?")).classes("job-name")
                                ui.link(f"#{j.get('id')}", f"/jobs/{j['id']}").classes("job-id")
                            status_pill(t("status.running"), "running")
                            ui.label(j.get("queue_name", "-")).classes("job-time")
            with ui.column().classes("w-full lg:w-[360px] gap-5"):
                with card(t("overview.failures.title"), t("overview.failures.description")):
                    if not failed:
                        empty_state(t("empty"))
                    for j in failed:
                        with ui.element("div").classes("job-row"):
                            with ui.column().classes("gap-0 flex-1 min-w-0"):
                                ui.label(j.get("task_name", "?")).classes("job-name")
                                ui.link(f"#{j.get('id')}", f"/jobs/{j['id']}").classes("job-id")
                            status_pill(t("status.failed"), "error")
