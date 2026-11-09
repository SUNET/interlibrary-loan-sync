from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BorrowingOrderRead(BaseModel):
    """A borrowing order as returned by the API.

    ``patron_barcode`` is deliberately absent. The caller already holds it,
    and echoing an identifier back widens where it can be logged or cached.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Beställnings-id (N1).")
    tenant_id: UUID
    state: str = Field(description="SUBMITTED | LINKED | CANCELLED")
    request_type: str
    processing_state: str = Field(
        description=(
            "HANDLED once the infodisk mail is confirmed, UNHANDLED while it "
            "is queued, retrying or abandoned."
        )
    )
    bibliographic: dict[str, Any]
    patron_name: str
    folio_user_status: str = Field(
        description=(
            "FOUND | NOT_FOUND | CHECK_FAILED. CHECK_FAILED means FOLIO could "
            "not be asked or could not be believed, which is not the same as "
            "the patron being absent."
        )
    )
    folio_user_id: UUID | None
    libris_lf_number: str | None = Field(
        description=(
            "Libris reference recorded by a human, either at creation or "
            "afterwards. A set reference is a claim, not a resolved link: "
            "only state == LINKED means the Libris request was matched."
        )
    )
    created_at: datetime.datetime
    updated_at: datetime.datetime
