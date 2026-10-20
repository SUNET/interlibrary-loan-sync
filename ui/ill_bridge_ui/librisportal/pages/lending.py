"""Utgående lån — material this library lends out to others (utlån).

These are the LENDING views: another library has asked us for something.
"""
from __future__ import annotations

from ill_bridge_ui.librisportal.pages._requests import ViewTab, render_requests_page

TABS: tuple[ViewTab, ...] = (
    ViewTab("incoming", "tab.incoming"),
    ViewTab("recent", "tab.recent"),
    ViewTab("reservations", "tab.reservations"),
    ViewTab("cancellations", "tab.cancellations"),
)


async def render() -> None:
    await render_requests_page(
        active="lending",
        eyebrow_key="lending.eyebrow",
        title_key="lending.title",
        description_key="lending.description",
        tabs=TABS,
    )
