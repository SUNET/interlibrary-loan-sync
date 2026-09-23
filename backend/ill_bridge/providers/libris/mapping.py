# ill_bridge/providers/libris/mapping.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

from ill_bridge.common.enums import ILLDirection, RequestType
from ill_bridge.common.exceptions import (
    InvalidLibrisRecord,
    UnknownLibrisMediaType,
)
from ill_bridge.common.models import (
    Bibliographic,
    Library,
    ProviderRequestObservation,
    ProviderRequests,
)
from ill_bridge.common.states import WorkflowState


@dataclass(frozen=True, slots=True)
class StatusMapping:
    """Interpretation of a Libris status code in the domain model."""

    state: WorkflowState
    confident: bool


class LibrisMappingProfile:
    """
    Maps and normalizes Libris records into provider-independent
    CanonicalObservation objects.

    The mapping profile contains only Libris-specific vocabulary and rules.
    """

    version: ClassVar[str] = "libris-v1"
    schema_version: ClassVar[int] = 1

    # Keyed on:
    #
    #     (status_code, direction, request_type)
    #
    # NOT status_code alone.
    #
    # Some Libris status codes have different meanings depending on the
    # verified direction/request type.
    STATUS_CODE_MAP: ClassVar[
        dict[
            tuple[str, ILLDirection | None, RequestType | None],
            StatusMapping,
        ]
    ] = {
        # Direction/type-independent statuses.
        ("1", None, None): StatusMapping(
            WorkflowState.REQUESTED,
            True,
        ),  # Uteliggande
        ("3", None, None): StatusMapping(
            WorkflowState.REQUESTED,
            True,
        ),  # Läst — read acknowledgement
        ("6", None, None): StatusMapping(
            WorkflowState.REJECTED,
            True,
        ),  # Negativt svar
        ("13", None, None): StatusMapping(
            WorkflowState.CANCELLED,
            True,
        ),  # Makulerad
        # Known status, but interpretation is not fully verified.
        ("4", None, None): StatusMapping(
            WorkflowState.ACCEPTED,
            False,
        ),  # Remitterad
        ("9", None, None): StatusMapping(
            WorkflowState.ACCEPTED,
            False,
        ),  # Reserverad
        # `10` Levererad — interpretation depends on context.
        ("10", ILLDirection.LENDING, RequestType.LOAN): StatusMapping(
            WorkflowState.IN_TRANSIT,
            True,
        ),
        ("10", ILLDirection.BORROWING, RequestType.LOAN): StatusMapping(
            WorkflowState.IN_TRANSIT,
            True,
        ),
        ("10", ILLDirection.LENDING, RequestType.COPY): StatusMapping(
            WorkflowState.FULFILLED,
            True,
        ),
        ("10", ILLDirection.BORROWING, RequestType.COPY): StatusMapping(
            WorkflowState.FULFILLED,
            True,
        ),
    }

    MEDIA_TYPE_CODE_MAP: ClassVar[dict[str, RequestType]] = {
        "1": RequestType.LOAN,
        "2": RequestType.COPY,
    }

    MODELLED_FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "lf_number",
            "request_id",
            "requesting_library",
            "active_library",
            "media_type_code",
            "media_type",
            "status_code",
            "status",
            "last_modified",
            "isbn_issn",
            "title",
            "title_of_article",
            "author",
            "author_of_article",
            "recipients",
            "receiving_library",
        }
    )

    def lookup_state(
        self,
        code: str,
        direction: ILLDirection,
        request_type: RequestType,
    ) -> StatusMapping | None:
        """
        Resolve the most specific status mapping first, then the
        direction/type-independent fallback.
        """
        return self.STATUS_CODE_MAP.get(
            (code, direction, request_type)
        ) or self.STATUS_CODE_MAP.get((code, None, None))

    @staticmethod
    def derive_direction(
        record: Mapping[str, Any],
        our_sigel: str,
    ) -> ILLDirection:
        """
        Determine whether the request is borrowing or lending.

        If our library is the requesting library, we are borrowing.
        Otherwise the request is treated as lending.
        """
        requesting_library = str(record.get("requesting_library") or "").strip()

        if requesting_library == our_sigel:
            return ILLDirection.BORROWING

        return ILLDirection.LENDING

    @classmethod
    def map_request_type(cls, media_code: str) -> RequestType:
        """Map a Libris media type code to the domain request type."""
        try:
            return cls.MEDIA_TYPE_CODE_MAP[media_code]
        except KeyError as exc:
            raise UnknownLibrisMediaType(media_code) from exc

    @staticmethod
    def _bibliographic(
        record: Mapping[str, Any],
    ) -> Bibliographic:
        identifiers: list[dict[str, str]] = []

        if isbn_issn := record.get("isbn_issn"):
            identifiers.append(
                {
                    "scheme": "ISBN",
                    "value": str(isbn_issn),
                }
            )

        authors: list[str] = []

        if author := record.get("author"):
            authors.append(str(author))

        return Bibliographic(
            title=record.get("title"),
            article_title=record.get("title_of_article"),
            authors=authors,
            identifiers=identifiers,
        )

    @classmethod
    def extract_extensions(
        cls,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Preserve provider fields not represented by the canonical model."""
        return {
            key: value
            for key, value in record.items()
            if key not in cls.MODELLED_FIELDS
        }

    @staticmethod
    def _required_string(
        record: Mapping[str, Any],
        field: str,
    ) -> str:
        value = record.get(field)

        if value is None or not str(value).strip():
            raise InvalidLibrisRecord(f"Missing required Libris field: {field}")

        return str(value)

    def normalize(
        self,
        record: Mapping[str, Any],
        *,
        our_sigel: str,
        observed_at: datetime,
        correlation_id: UUID | None = None,
    ) -> ProviderRequestObservation:
        """
        Convert one raw Libris record into a canonical observation.

        Unknown status codes are preserved as unmapped observations.
        Unknown media types are rejected because treating them as LOAN
        would create false domain information.
        """
        lf_number = self._required_string(record, "lf_number")

        direction = self.derive_direction(
            record,
            our_sigel,
        )

        media_code = self._required_string(
            record,
            "media_type_code",
        )

        request_type = self.map_request_type(media_code)

        status_code = str(record.get("status_code") or "")

        mapped = self.lookup_state(
            status_code,
            direction,
            request_type,
        )

        requesting_library = str(record.get("requesting_library") or "").strip()

        active_library = record.get("active_library")

        provider_record_id = (
            str(record["request_id"]) if record.get("request_id") else None
        )

        provider_revision = record.get("last_modified")

        event_key = (
            f"{lf_number}:{provider_revision}"
            if provider_revision is not None
            else lf_number
        )

        return ProviderRequestObservation(
            schema_version=self.SCHEMA_VERSION,
            external_request_id=lf_number,
            provider_record_id=provider_record_id,
            direction=direction,
            request_type=request_type,
            requesting_library=Library(
                value=requesting_library,
            ),
            active_lending_library=(
                Library(value=str(active_library)) if active_library else None
            ),
            bibliographic=self._bibliographic(record),
            provider_status_raw=record.get("status"),
            provider_status_code=status_code or None,
            provider_revision=provider_revision,
            observed_at=observed_at,
            extensions=self.extract_extensions(record),
            mapped_state=mapped.state if mapped else None,
            mapping_confident=mapped.confident if mapped else False,
            event_key=event_key,
            correlation_id=correlation_id or uuid4(),
        )
