"""Unit tests for the FOLIO patron lookup (A5).

``find_patron`` is the one FOLIO call on the order-intake path. Its contract
is unusual and load-bearing: it must *never raise* and must distinguish
"patron absent" (``NOT_FOUND``) from "could not ask / could not believe the
answer" (``CHECK_FAILED``), because the infodisk mail says different things
for each. These tests pin that contract down with an in-process fake FOLIO
client -- no network, no real credentials.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from ill_bridge.common.states import FolioUserStatus
from ill_bridge.folio.users import PatronLookup, find_patron

FOLIO_USER_ID = UUID("11111111-2222-3333-4444-555555555555")


def test_single_match_is_found_with_id(folio_client_factory) -> None:
    client = folio_client_factory(users=[{"id": str(FOLIO_USER_ID)}])

    result = asyncio.run(find_patron(client, barcode="900123"))

    assert result == PatronLookup(FolioUserStatus.FOUND, FOLIO_USER_ID)
    assert result.found is True
    # The barcode is sent as a quoted CQL term with a limit of 2 so a second
    # match can be detected.
    endpoint, params = client.calls[0]
    assert endpoint == "users"
    assert params["query"] == 'barcode=="900123"'
    assert params["limit"] == 2


def test_no_match_is_not_found(folio_client_factory) -> None:
    client = folio_client_factory(users=[])

    result = asyncio.run(find_patron(client, barcode="nobody"))

    assert result == PatronLookup(FolioUserStatus.NOT_FOUND)
    assert result.found is False


def test_multiple_matches_is_check_failed(folio_client_factory) -> None:
    # FOLIO holds barcodes unique, so two hits means the lookup's assumption
    # is wrong; picking the first would attach the loan to the wrong person.
    client = folio_client_factory(
        users=[{"id": str(FOLIO_USER_ID)}, {"id": str(UUID(int=9))}]
    )

    result = asyncio.run(find_patron(client, barcode="dupe"))

    assert result == PatronLookup(FolioUserStatus.CHECK_FAILED)


def test_missing_client_is_check_failed() -> None:
    # A misconfigured FOLIO must not stop an order being created: the check
    # is skipped and reported, never raised.
    result = asyncio.run(find_patron(None, barcode="900123"))

    assert result == PatronLookup(FolioUserStatus.CHECK_FAILED)


def test_transport_error_is_check_failed(folio_client_factory) -> None:
    client = folio_client_factory(raise_on_get=ConnectionError("FOLIO down"))

    result = asyncio.run(find_patron(client, barcode="900123"))

    assert result == PatronLookup(FolioUserStatus.CHECK_FAILED)


def test_http_error_is_check_failed(folio_client_factory) -> None:
    # raise_for_status() raising is swallowed into CHECK_FAILED just like a
    # transport error -- intake cannot tell the difference and must not care.
    client = folio_client_factory(status_code=500)

    result = asyncio.run(find_patron(client, barcode="900123"))

    assert result == PatronLookup(FolioUserStatus.CHECK_FAILED)


def test_unusable_user_id_is_check_failed(folio_client_factory) -> None:
    client = folio_client_factory(users=[{"id": "not-a-uuid"}])

    result = asyncio.run(find_patron(client, barcode="900123"))

    assert result == PatronLookup(FolioUserStatus.CHECK_FAILED)


def test_barcode_with_quotes_is_escaped_for_cql(folio_client_factory) -> None:
    # A raw double quote would terminate the CQL term early; it must be
    # backslash-escaped, and the backslash itself escaped first.
    client = folio_client_factory(users=[])

    asyncio.run(find_patron(client, barcode='9\\0"1'))

    _, params = client.calls[0]
    assert params["query"] == 'barcode=="9\\\\0\\"1"'
