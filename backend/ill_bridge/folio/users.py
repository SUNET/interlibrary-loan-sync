"""FOLIO user lookups for the borrowing flow (A5).

The patron check runs *before* the order is written, because its outcome is
stored on the order and quoted in the infodisk mail. It therefore must never
raise and never block: an order is created whatever FOLIO says, or fails to
say.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from ill_bridge.common.folio_client import FolioApiClient
from ill_bridge.common.states import FolioUserStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PatronLookup:
    """Outcome of one FOLIO patron check."""

    status: FolioUserStatus
    folio_user_id: UUID | None = None

    @property
    def found(self) -> bool:
        return self.status is FolioUserStatus.FOUND


def _cql_quote(value: str) -> str:
    r"""Escape a value for use inside a double-quoted CQL term.

    A barcode is caller-supplied, so it cannot be interpolated raw: a ``"``
    would terminate the term early and the rest would be parsed as query
    syntax. CQL escapes with a backslash, and the backslash itself must be
    escaped first.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def find_patron(
    client: FolioApiClient | None,
    *,
    barcode: str,
) -> PatronLookup:
    """Look a patron up in FOLIO by barcode.

    Returns, never raises:

    * ``FOUND`` with the user id, when exactly one user matches.
    * ``NOT_FOUND`` when FOLIO answered and no user matches.
    * ``CHECK_FAILED`` when FOLIO could not be asked or could not be
      believed. That covers an unreachable FOLIO, an unexpected response
      shape, and a barcode matching more than one user.

    ``CHECK_FAILED`` is deliberately distinct from ``NOT_FOUND``: telling the
    infodisk "hittades inte" when the truth is "we could not ask" would send
    staff looking for a patron problem that does not exist.

    More than one match is treated as a failure rather than resolved by
    taking the first hit. FOLIO holds barcodes unique, so two matches means
    the assumption behind this lookup is wrong, and silently picking a patron
    would attach the loan to the wrong person.
    """
    if client is None:
        logger.warning("no FOLIO client configured; patron check skipped")
        return PatronLookup(FolioUserStatus.CHECK_FAILED)

    try:
        response = await client.get(
            "users",
            params={"query": f'barcode=="{_cql_quote(barcode)}"', "limit": 2},
        )
        response.raise_for_status()
        users = response.json().get("users", [])
    except Exception:
        # Intentionally broad: transport errors, HTTP errors, malformed JSON
        # and auth failures all mean the same thing to intake -- we did not
        # get an answer -- and none of them may stop the order being created.
        logger.exception("FOLIO patron check failed")
        return PatronLookup(FolioUserStatus.CHECK_FAILED)

    if not users:
        return PatronLookup(FolioUserStatus.NOT_FOUND)

    if len(users) > 1:
        logger.error(
            "FOLIO returned %d users for one barcode; treating as CHECK_FAILED",
            len(users),
        )
        return PatronLookup(FolioUserStatus.CHECK_FAILED)

    raw_id = users[0].get("id")
    try:
        return PatronLookup(FolioUserStatus.FOUND, UUID(str(raw_id)))
    except (TypeError, ValueError):
        logger.error("FOLIO user has unusable id %r", raw_id)
        return PatronLookup(FolioUserStatus.CHECK_FAILED)
