from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ill_bridge.common.enums import RequestType



class BorrowingOrderCreate(BaseModel):
    """Body of ``POST /api/v1/borrowing/orders`` (A5).

    Sent by the discovery layer once the patron has completed the form.
    """

    model_config = ConfigDict(extra="forbid")

    order_id: UUID | None = Field(
        default=None,
        description=(
            "Order id, chosen by the caller. This is the beställnings-id "
            "staff and the patron see, and it is the idempotency key: "
            "re-sending the same id returns the existing order instead of "
            "creating a second one. Omit it and every retry creates a new "
            "order and a second mail to the infodisk."
        ),
    )
    request_type: RequestType = Field(
        description="LOAN for the item itself, COPY for an article copy."
    )
    bibliographic: dict[str, Any] = Field(
        description="Bibliographic data prefilled by discovery (A4)."
    )
    patron_barcode: str = Field(
        min_length=1,
        max_length=255,
        description="Library card number, used for the FOLIO patron check.",
    )
    patron_name: str = Field(
        min_length=1,
        max_length=255,
        description="Patron name (N1 låntagarens namn).",
    )
    libris_lf_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "Libris reference, when the Libris request already exists. "
            "Optional: in the normal A5 flow the Libris request has not been "
            "created yet, so this is left out and a librarian records it "
            "afterwards with PATCH. Supplying it does not make the order "
            "LINKED -- it records what a human typed, not a resolved link."
        ),
    )


class BorrowingOrderUpdate(BaseModel):
    """Body of ``PATCH /api/v1/borrowing/orders/{order_id}``.

    Step 5 of the A6 linking sequence: a librarian creates the request by
    hand in Libris, Libris returns an ``lf_number``, and the librarian brings
    it back here. Also how a typo is corrected, and how a re-order after
    ``notfullfilled`` records its new reference.
    """

    model_config = ConfigDict(extra="forbid")

    libris_lf_number: str | None = Field(
        min_length=1,
        max_length=64,
        description=(
            "Libris reference to record. Null clears it. At most one order "
            "per tenant may claim a given reference."
        ),
    )
