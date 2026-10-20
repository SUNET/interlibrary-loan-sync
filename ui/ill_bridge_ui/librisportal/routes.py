"""URL routing for the librisportal.

Kept separate from ``main.py`` so tests can register pages against a fresh
NiceGUI app without invoking ``ui.run``.
"""
from __future__ import annotations

from nicegui import ui

from ill_bridge_ui.librisportal.pages import borrowing, lending, libraries


def register_pages() -> None:
    """Bind :func:`ui.page` decorators for every librisportal route."""

    @ui.page("/")
    async def _lending() -> None:
        await lending.render()

    @ui.page("/inkommande")
    async def _borrowing() -> None:
        await borrowing.render()

    @ui.page("/bibliotek")
    async def _libraries() -> None:
        await libraries.render()
