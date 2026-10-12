from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pprint import pformat
from typing import Any
from uuid import UUID, uuid4

from ill_bridge.common.enums import ILLDirection, RequestType, ProviderCommand
from ill_bridge.common.states import WorkflowState
from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True, slots=True)
class FolioPatronGroup:
    name: str
    uuid: str | None = None

@dataclass(frozen=True, slots=True)
class ProviderRequests:
    feed: str
    count: int
    requests: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ProviderCapabilities:
    directions: frozenset[ILLDirection]
    request_types: frozenset[RequestType]
    commands: frozenset[ProviderCommand]
    supports_webhooks: bool = False
    supports_cursors: bool = False        # Libris: no cursor, no pagination
    native_idempotency: bool = False

class PatronReference(BaseModel):
    """A local patron identifier (before resolution against FOLIO), pre-resolution."""

    model_config = ConfigDict(strict=True)

    type: str  # "BARCODE" | "FOLIO_USER_ID" | "LIBRARY_CARD"
    value: str
    # Set once resolved against FOLIO in Part 6; None means unmatched.
    folio_user_id: str | None = None


class Library(BaseModel):
    model_config = ConfigDict(strict=True)

    scheme: str = "SIGEL"
    value: str  # e.g. "Hal"
    display_name: str | None = None


class ReceivingLibrary(BaseModel):
    model_config = ConfigDict(strict=True)

    library_code: str
    name: str
    department: str | None = None
    address1: str | None = None
    address2: str | None = None
    address3: str | None = None
    zip_code: str | None = None
    city: str | None = None
    fax: str | None = None
    email: str | None = None
    bibsam: bool | None = False
    
    

class RequestParty(BaseModel):
    model_config = ConfigDict(strict=True)

    library_id: str
    library_code: str
    is_active_library: bool
    location: str | None = None
    response_id: str | None = None
    response: str | None = None
    response_date: datetime | None = None
    reserve: bool | None = False

class LocalStatus(BaseModel):
    model_config = ConfigDict(strict=True)
    
    status: str
    code: str

class Bibliographic(BaseModel):
    model_config = ConfigDict(strict=True)

    authors: list[str] = Field(default_factory=list)
    title: str | None = None
    container_title: str | None = None
    article_title: str | None = None
    publication_year: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    identifiers: list[dict[str, str]] = Field(default_factory=list)


class ProviderRequestObservation(BaseModel):
    """
    An observation describes what the provider returned at a specific instant
    for one request from the providerRequests feed.
    not the actions taken in response.
    The decision is based on `states.transition()`.
    """

    model_config = ConfigDict(strict=True)

    schema_version: int = 1

    # Staff-facing identifier. For Libris this is `lf_number`; `request_id`
    external_request_id: str
    provider_record_id: str | None = None

    direction: ILLDirection
    request_type: RequestType

    requesting_library: Library
    active_lending_library: Library | None = None
    receiving_library: ReceivingLibrary | None = None
    recipients: list[RequestParty] = Field(default_factory=list)
    local_status: LocalStatus | None = None

    bibliographic: Bibliographic
    patron_reference: PatronReference | None = None

    # Raw provider status is ALWAYS preserved next to the mapped state.
    provider_status_raw: str | None = None
    provider_status_code: str | None = None

    # Opaque revision token for optimistic concurrency.
    # Libris=`last_modified`, a Unix-epoch STRING.
    provider_revision: str | None = None

    observed_at: datetime

    # Provider fields we do not model yet.
    extensions: dict[str, Any] = Field(default_factory=dict)

    # The state `provider_status_code` maps to under the active mapping
    # profile, and whether that mapping is VERIFIED against real traffic.
    mapped_state: WorkflowState | None = None
    mapping_confident: bool = False

    # Identifies the exact upstream revision this observation came from,
    # `lf_number:last_modified`. Used for dedup and echo suppression.
    event_key: str
    correlation_id: UUID = Field(default_factory=uuid4)

    @property
    def needs_review(self) -> bool:
        return self.mapped_state is None or not self.mapping_confident

    def __repr_str__(self, join_str: str) -> str:
        fields = ",\n    ".join(
            f"{name}={pformat(value, width=100, sort_dicts=False)}"
            for name, value in self.__repr_args__()
        )
        return f"\n    {fields}\n"
    
    def short_repr(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"external_request_id={self.external_request_id!r}, "
            f"request_type={self.request_type.value!r}, "
            f"provider_status_raw={self.provider_status_raw!r}, "
            f"status_code={self.provider_status_code!r}, "
            f"direction={self.direction.value!r}, "
            f"mapped_state={self.mapped_state.value if self.mapped_state else None!r}, "
            f"mapping_confident={self.mapping_confident!r}, "
            f"patron_reference={self.patron_reference!r}, "
            f"receiving_library={self.receiving_library!r}, "
            f"recipients={self.recipients!r}, "
            f"local_status={self.local_status!r}, "
            ")"
        )
    
    def __repr__(self):
        return super().__repr__()

    def __str__(self) -> str:
        return self.short_repr()