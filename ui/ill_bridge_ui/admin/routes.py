"""URL routing for the admin portal.

Kept separate from ``main.py`` so tests can register pages against a fresh
NiceGUI app without invoking ``ui.run``. Pages themselves are async coroutine
factories — NiceGUI awaits them per request.
"""
from __future__ import annotations

from nicegui import ui

from ill_bridge_ui.admin.pages import overview, jobs, job_detail, queues, workers
from ill_bridge_ui.shared.i18n import t


def register_pages() -> None:
    """Bind :func:`ui.page` decorators for every admin route."""

    @ui.page("/")
    async def _overview() -> None:
        await overview.render()

    @ui.page("/jobs")
    async def _jobs() -> None:
        await jobs.render()

    @ui.page("/jobs/{job_id:int}")
    async def _job_detail(job_id: int) -> None:
        await job_detail.render(job_id)

    @ui.page("/queues")
    async def _queues() -> None:
        await queues.render()

    @ui.page("/workers")
    async def _workers() -> None:
        await workers.render()

    # Stubbed views — sidebar shows them but pages just say "coming soon".
    for path, key in (("/libris", "nav.libris"),
                      ("/schedules", "nav.schedules"),
                      ("/failures", "nav.failures"),
                      ("/events", "nav.events")):
        _register_stub(path, key)


def _register_stub(path: str, label_key: str) -> None:
    """Register a placeholder page so nav links do not 404."""
    from ill_bridge_ui.admin.nav_config import ADMIN_NAV
    from ill_bridge_ui.shared.layout import page_shell

    # Find the nav key for the active-highlight to match the route.
    active = next(
        (item.key for group in ADMIN_NAV for item in group.items if item.route == path),
        "",
    )

    @ui.page(path)
    async def _stub() -> None:
        from ill_bridge_ui.shared.components import card, empty_state
        from ill_bridge_ui.shared.layout import page_header

        with page_shell(ADMIN_NAV, active=active):
            page_header("stub.eyebrow", label_key, "stub.description")
            with card(t(label_key), t("stub.description")):
                empty_state(t("stub.coming_soon"))
