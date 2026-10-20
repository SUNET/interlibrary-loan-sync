"""Reusable UI primitives.

These wrap Quasar's own components (``ui.card``, ``ui.table``) rather than
hand-rolled ``<div>``s. Quasar already handles borders, elevation, responsive
table scrolling and sticky headers — re-implementing that in CSS is what made
the first iteration look broken. We only add a thin layer of SUNET styling on
top via the classes defined in ``global.css``.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Iterator

from nicegui import html, ui


def text_el(tag: str, text: str, classes: str = "") -> ui.element:
    """Render ``<tag class="classes">text</tag>`` with a real text node.

    NiceGUI's generic :func:`ui.element` has **no** ``text`` property — assigning
    ``ui.element('div').text = 'x'`` silently sets a dead Python attribute and
    renders an empty tag. ``nicegui.html.<tag>(value)`` populates the element's
    internal ``_text`` instead, which the frontend renders as an escaped text
    child. Use this for semantic tags; prefer ``ui.label`` for plain text.
    """
    factory = getattr(html, tag, None)
    if factory is None:  # pragma: no cover - guards typos in tag names
        raise ValueError(f"unknown html tag: {tag!r}")
    el = factory(str(text))
    return el.classes(classes) if classes else el


def card_header(title: str, subtitle: str | None = None,
                right: Callable[[], None] | None = None) -> None:
    """Title bar inside a ``p-0`` card. ``right`` renders trailing content."""
    with ui.row().classes("card-header w-full items-center justify-between gap-4 px-5 py-4"):
        with ui.column().classes("gap-0"):
            ui.label(title).classes("font-bold text-base")
            if subtitle:
                ui.label(subtitle).classes("text-xs light")
        if right:
            right()


@contextmanager
def card(title: str | None = None, subtitle: str | None = None, *,
         extra_classes: str = "", padded: bool = False,
         right: Callable[[], None] | None = None) -> Iterator[ui.element]:
    """A Quasar card with an optional header and a body slot.

    The card itself is ``p-0`` so headers and tables sit edge-to-edge; pass
    ``padded=True`` to get a padded body for prose or free-form content.

    Usage::

        with card("Recent jobs", "Last 20 completions"):
            styled_table(...)
    """
    with ui.card().classes(f"w-full p-0 gap-0 overflow-hidden {extra_classes}".strip()) as root:
        if title is not None:
            card_header(title, subtitle, right)
        if padded:
            with ui.column().classes("w-full p-5 gap-3"):
                yield root
        else:
            yield root


def metric(label: str, value: str | int, *, meta: str | None = None,
           meta_kind: str | None = None) -> None:
    """A KPI tile. ``meta_kind`` in {success, warning, error}."""
    with ui.card().classes("metric-card p-4 gap-0 w-full"):
        ui.label(label).classes("metric-label")
        ui.label(str(value)).classes("metric-value mt-1")
        if meta is not None:
            cls = "metric-meta mt-1" + (f" {meta_kind}" if meta_kind else "")
            ui.label(meta).classes(cls)


@contextmanager
def metric_grid(columns: int = 5) -> Iterator[ui.element]:
    """Responsive container for a row of :func:`metric` tiles.

    ``columns`` is the count at the widest breakpoint and should match the
    number of tiles, otherwise the last row is left with a ragged gap. The
    intermediate step is always 2 rather than 3 so a 4-tile grid never lands
    on an uneven 3 + 1.
    """
    with ui.grid().classes(
        f"w-full gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-{columns}"
    ) as root:
        yield root


def status_pill(label: str, kind: str = "neutral") -> None:
    """Small pill matching ``.status-{running,success,warning,error,neutral}``."""
    ui.html(f'<span class="status status-{kind}">{label}</span>')


# --- table helpers -------------------------------------------------------

# Maps a backend job/queue status onto a ``.status-*` modifier. Anything not
# listed renders neutral, so new Procrastinate statuses degrade gracefully.
STATUS_KIND = {
    "doing": "running",
    "running": "running",
    "succeeded": "success",
    "failed": "error",
    "todo": "neutral",
    "cancelled": "neutral",
    "aborting": "warning",
    "aborted": "warning",
}


def styled_table(columns: list[dict], rows: list[dict], *,
                 row_key: str = "id",
                 status_column: str | None = "status") -> ui.table:
    """A Quasar table matching the reference design.

    Left-aligns every column by default (Quasar's default is right, which is
    what made the tables look "weird") and renders ``status_column`` as a
    coloured pill via a ``body-cell-<name>`` scoped slot.
    """
    cols = [{"align": "left", **c} for c in columns]
    table = ui.table(columns=cols, rows=rows, row_key=row_key).classes("w-full")

    if status_column and any(c["name"] == status_column for c in cols):
        kinds = ",".join(f"'{k}':'{v}'" for k, v in STATUS_KIND.items())
        table.add_slot(f"body-cell-{status_column}", f"""
            <q-td :props="props">
                <span class="status"
                      :class="'status-' + (({{{kinds}}})[props.value] || 'neutral')">
                    {{{{ props.value }}}}
                </span>
            </q-td>
        """)
    return table


def empty_state(message: str) -> None:
    """Consistent empty-state line inside a card body."""
    ui.label(message).classes("muted text-sm p-5")


def request_table(columns: list[dict], rows: list[dict], *,
                  row_key: str = "request_id") -> ui.table:
    """Table for Libris ILL records produced by ``libris_records.to_row``.

    Two slots differ from :func:`styled_table`:

    * ``title`` renders the item title with a dimmed identifier line beneath it
      (ISBN · author · year), because a bare title is rarely enough to tell two
      editions apart at a glance;
    * ``status`` colours the pill from the row's precomputed ``status_tone``
      rather than matching on the display string — Libris' ``status`` text has
      drifted between the docs and the live API, but the codes have not.
    """
    cols = [{"align": "left", **c} for c in columns]
    table = ui.table(columns=cols, rows=rows, row_key=row_key).classes("w-full")

    names = {c["name"] for c in cols}
    if "title" in names:
        table.add_slot("body-cell-title", """
            <q-td :props="props">
                <div class="item-title">{{ props.row.title }}</div>
                <div class="item-meta" v-if="props.row.subtitle">
                    {{ props.row.subtitle }}
                </div>
            </q-td>
        """)
    if "library" in names:
        table.add_slot("body-cell-library", """
            <q-td :props="props">
                <div class="item-title">{{ props.row.library }}</div>
                <div class="item-meta" v-if="props.row.library_code">
                    {{ props.row.library_code }}
                </div>
            </q-td>
        """)
    if "status" in names:
        table.add_slot("body-cell-status", """
            <q-td :props="props">
                <span class="status" :class="'status-' + props.row.status_tone">
                    {{ props.row.status }}
                </span>
            </q-td>
        """)
    return table

