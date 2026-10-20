"""Presentation helpers for raw Libris ILL records.

Libris returns ~50 fields per request, most of which a librarian never needs.
These helpers pick out the handful that drive the daily workflow and translate
Libris' numeric status codes into the UI's ``.status-*`` tones.

Kept separate from the client so the client stays a faithful transport layer
and all the "what does this mean to a human" logic lives in one reviewable place.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# Status codes verified against 2 189 real records (docs/part1_conclusion.md §2).
# Mapping is on the *code*; `status` is a display string and has drifted before
# (the docs say "Ej läst", the live API returns "Oläst").
STATUS_TONE = {
    "1": "warning",   # Uteliggande — outstanding, awaiting a response
    "3": "neutral",   # Läst
    "4": "running",   # Remitterad — referred onward
    "6": "error",     # Negativt svar
    "9": "running",   # Reserverad
    "10": "success",  # Levererad
    "13": "neutral",  # Makulerad
}

# Codes that mean "this request still needs someone to act on it". Drives the
# action-required KPI and the default sort.
ACTIONABLE_CODES = {"1", "9"}


def status_tone(record: dict[str, Any]) -> str:
    """``.status-*`` modifier for a record's status code."""
    return STATUS_TONE.get(str(record.get("status_code", "")), "neutral")


def counterparty(record: dict[str, Any], our_sigel: str) -> str:
    """The *other* library in this transaction, as a sigel.

    Libris names the two sides ``requesting_library`` (who asked) and
    ``active_library`` (who is handling it). Which one is "them" depends on the
    direction, so pick whichever is not us rather than always taking one side:
    on a borrowing record we are the requester, on a lending record we are the
    active library. Taking ``requesting_library`` unconditionally renders our
    own sigel on every borrowing row.

    ``receiving_library.library_code`` is preferred when present, but it is
    absent from generated fixtures, so it cannot be the only source.
    """
    requesting = str(record.get("requesting_library") or "")
    active = str(record.get("active_library") or "")
    receiving = record.get("receiving_library") or {}

    if isinstance(receiving, dict):
        code = str(receiving.get("library_code") or "")
        if code and code != our_sigel:
            return code

    if requesting and requesting != our_sigel:
        return requesting
    if active and active != our_sigel:
        return active
    # Both sides are us (or the record is malformed) — show whatever we have.
    return requesting or active or "—"


def counterparty_name(record: dict[str, Any], our_sigel: str) -> str:
    """Human-readable name of the other library, falling back to its sigel."""
    receiving = record.get("receiving_library") or {}
    if isinstance(receiving, dict) and receiving.get("name"):
        return str(receiving["name"])
    return counterparty(record, our_sigel)


def title(record: dict[str, Any]) -> str:
    """Item title. Copies carry the article title; loans carry the book title.

    Real Libris titles include ISBD punctuation and the statement of
    responsibility (``"Some title / Some Author."``); we show them verbatim
    rather than trying to strip it, because librarians recognise that shape.
    """
    return str(record.get("title_of_article") or record.get("title") or "—")


def subtitle(record: dict[str, Any]) -> str:
    """Secondary identifier line shown under the title."""
    parts: list[str] = []
    if isbn := record.get("isbn_issn"):
        parts.append(str(isbn))
    if author := (record.get("author_of_article") or record.get("author")):
        parts.append(str(author))
    if year := record.get("year"):
        parts.append(str(year))
    return " · ".join(parts)


def last_modified_at(record: dict[str, Any]) -> datetime | None:
    """Parse ``last_modified`` for *display only*.

    Never send the parsed value back: the API compares the epoch string
    verbatim for optimistic concurrency, so a reserialised value is rejected.
    """
    raw = record.get("last_modified")
    if not raw:
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=UTC)
    except (TypeError, ValueError):
        return None


def last_modified_display(record: dict[str, Any]) -> str:
    dt = last_modified_at(record)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


def to_row(record: dict[str, Any], our_sigel: str) -> dict[str, Any]:
    """Flatten a Libris record into a Quasar table row."""
    return {
        "request_id": str(record.get("request_id", "")),
        "lf_number": record.get("lf_number") or "—",
        "title": title(record),
        "subtitle": subtitle(record),
        "library": counterparty_name(record, our_sigel),
        "library_code": counterparty(record, our_sigel),
        "media_type": record.get("media_type") or "—",
        "status": record.get("status") or "—",
        "status_tone": status_tone(record),
        "updated": last_modified_display(record),
        "actionable": str(record.get("status_code")) in ACTIONABLE_CODES,
    }


def to_rows(records: list[dict[str, Any]], our_sigel: str) -> list[dict[str, Any]]:
    return [to_row(r, our_sigel) for r in records]


def count_actionable(records: list[dict[str, Any]]) -> int:
    return sum(1 for r in records if str(r.get("status_code")) in ACTIONABLE_CODES)
