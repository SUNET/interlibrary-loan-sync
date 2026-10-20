"""Data model for the sidebar navigation.

Kept in one place so both portals can define their own list of items without
inventing their own render logic. The shell in :mod:`layout.shell` walks
these groups to render the sidebar.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NavItem:
    """A single sidebar entry.

    Attributes:
        key: Stable identifier used to mark the active item.
        route: URL path this item links to.
        label_key: i18n key resolved at render time via :func:`i18n.t`.
        icon: A Material Icons name, rendered via ``ui.icon``.
        badge: Optional badge text (e.g. an unread count). Computed by the
            page host, not the nav — the sidebar just renders what it gets.
    """

    key: str
    route: str
    label_key: str
    icon: str
    badge: str | None = None


@dataclass(frozen=True)
class NavGroup:
    """A labelled group of :class:`NavItem` entries."""

    label_key: str
    items: tuple[NavItem, ...] = field(default_factory=tuple)
