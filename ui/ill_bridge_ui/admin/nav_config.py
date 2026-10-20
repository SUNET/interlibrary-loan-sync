"""Sidebar layout for the admin portal.

Data-driven: adding a view is one entry, not a new component.
"""
from __future__ import annotations

from ill_bridge_ui.shared.layout import NavGroup, NavItem

# NOTE: routes are root-relative — the admin portal is its own process/container,
# so it owns "/" and everything under it.
ADMIN_NAV: tuple[NavGroup, ...] = (
    NavGroup(
        label_key="nav.group.operations",
        items=(
            NavItem("overview", "/",          "nav.overview", "dashboard"),
            NavItem("jobs",     "/jobs",      "nav.jobs",     "work"),
            NavItem("workers",  "/workers",   "nav.workers",  "dns"),
            NavItem("queues",   "/queues",    "nav.queues",   "list"),
        ),
    ),
    NavGroup(
        label_key="nav.group.integration",
        items=(
            NavItem("libris",    "/libris",    "nav.libris",    "sync"),
            NavItem("schedules", "/schedules", "nav.schedules", "schedule"),
        ),
    ),
    NavGroup(
        label_key="nav.group.diagnostics",
        items=(
            NavItem("failures", "/failures", "nav.failures", "error_outline"),
            NavItem("events",   "/events",   "nav.events",   "timeline"),
        ),
    ),
)
