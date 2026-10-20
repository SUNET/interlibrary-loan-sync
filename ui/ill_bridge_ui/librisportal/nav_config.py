"""Sidebar layout for the librisportal.

Only three destinations: the two loan directions a librarian works in, plus
the library directory. Deliberately small — this portal is task-oriented, not
a systems console.
"""
from __future__ import annotations

from ill_bridge_ui.shared.layout import Brand, NavGroup, NavItem

# Librarian-facing branding — distinct from the admin portal's ops framing.
LIBRIS_BRAND = Brand(
    subtitle_key="brand.libris.subtitle",
    tagline_key="brand.libris.tagline",
)

LIBRIS_NAV: tuple[NavGroup, ...] = (
    NavGroup(
        label_key="nav.group.ill",
        items=(
            NavItem("lending", "/", "nav.lending", "north_east"),
            NavItem("borrowing", "/inkommande", "nav.borrowing", "south_west"),
        ),
    ),
    NavGroup(
        label_key="nav.group.admin",
        items=(
            NavItem("libraries", "/bibliotek", "nav.libraries", "account_balance"),
        ),
    ),
)
