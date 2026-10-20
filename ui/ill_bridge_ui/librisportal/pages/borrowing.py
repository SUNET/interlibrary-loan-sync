"""Inkommande lån — material this library borrows from others (inlån).

These are the BORROWING views: we have asked another library for something.
"""
from __future__ import annotations

from ill_bridge_ui.librisportal.pages._requests import ViewTab, render_requests_page

TABS: tuple[ViewTab, ...] = (
    ViewTab("inbox", "tab.inbox"),
    ViewTab("may_reserve", "tab.may_reserve"),
    ViewTab("notfullfilled", "tab.notfullfilled"),
    ViewTab("delivered", "tab.delivered"),
)


async def render() -> None:
    await render_requests_page(
        active="borrowing",
        eyebrow_key="borrowing.eyebrow",
        title_key="borrowing.title",
        description_key="borrowing.description",
        tabs=TABS,
    )
