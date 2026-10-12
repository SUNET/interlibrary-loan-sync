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
    LocalStatus,
    ProviderRequestObservation,
    ProviderRequests,
    ReceivingLibrary,
    RequestParty,
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
        ("2", None, None): StatusMapping(
            WorkflowState.RECEIVED,
            True,
        ),  # Requester has received the request and informed with local status code 2 (Mottagen)
        ("3", None, None): StatusMapping(
            WorkflowState.ACKNOWLEDGED,
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
            WorkflowState.RESERVED,
            True,
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
        ("11", ILLDirection.LENDING, RequestType.LOAN): StatusMapping(
            WorkflowState.CANCELLED,
            True,
        ),  # Cancel status_code = 11, status=Avbeställd
    }

    # Requesting library's own post-delivery tracking (`local_status_code`).
    #
    # This is a SEPARATE code namespace from `status_code`: e.g. local "3"
    # (Omlån) must never be read as status "3" (Läst). Same key shape as
    # STATUS_CODE_MAP: (local_status_code, direction, request_type).
    #
    # Only consulted once the request has been delivered (see
    # POST_DELIVERY_STATUS_CODES); "0" means no local status is set.
    LOCAL_STATUS_CODE_MAP: ClassVar[
        dict[
            tuple[str, ILLDirection | None, RequestType | None],
            StatusMapping,
        ]
    ] = {
        ("1", None, None): StatusMapping(
            WorkflowState.ARRIVED,
            True,
        ),  # Anländ — item has arrived at the requesting library
        ("2", None, None): StatusMapping(
            WorkflowState.RECEIVED,
            True,
        ),  # Mottagen — requester has received the item/ it is on loan to the patron
        ("3", None, None): StatusMapping(
            WorkflowState.RENEWAL_REQUESTED,
            True,
        ),  # Omlån — renewed; loan is still active
        # 'local_status': 'Återlämnad', 'local_status_code': '5'
        ("5", None, None): StatusMapping(
            WorkflowState.RETURNED_FROM_PATRON,
            True,
        ),  # Återlämnad — returned from patron, but not yet returned to lending library
        # 'local_status': 'Returnerad', 'local_status_code': '6'
        ("6", None, None): StatusMapping(
            WorkflowState.RETURN_IN_TRANSIT,
            True,
        ),  # Returnerad — returned to lending library, but not yet received
        # TODO: verify remaining local codes (Återsänd, Avslutad, ...)
    }

    # `status_code` values after which `local_status_code` becomes meaningful.
    POST_DELIVERY_STATUS_CODES: ClassVar[frozenset[str]] = frozenset({"10"})

    # `status_code` values that always win over any local status.
    TERMINAL_STATUS_CODES: ClassVar[frozenset[str]] = frozenset({"6", "11", "13"})

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
            "local_status_code",
            "local_status",
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

    @staticmethod
    def _lookup(
        status_map: Mapping[
            tuple[str, ILLDirection | None, RequestType | None], StatusMapping
        ],
        code: str,
        direction: ILLDirection,
        request_type: RequestType,
    ) -> StatusMapping | None:
        """Most specific mapping first, then the direction/type-independent one."""
        return status_map.get((code, direction, request_type)) or status_map.get(
            (code, None, None)
        )

    def lookup_state(
        self,
        code: str,
        direction: ILLDirection,
        request_type: RequestType,
    ) -> StatusMapping | None:
        """Resolve a Libris `status_code`."""
        return self._lookup(self.STATUS_CODE_MAP, code, direction, request_type)

    def lookup_local_state(
        self,
        code: str,
        direction: ILLDirection,
        request_type: RequestType,
    ) -> StatusMapping | None:
        """Resolve a Libris `local_status_code`."""
        return self._lookup(self.LOCAL_STATUS_CODE_MAP, code, direction, request_type)

    def resolve_state(
        self,
        status_code: str,
        local_status_code: str,
        direction: ILLDirection,
        request_type: RequestType,
    ) -> StatusMapping | None:
        """
        Combine `status_code` and `local_status_code` into one mapping.

        1. A terminal status (rejected/cancelled) always wins.
        2. After delivery, a known local status refines the state.
        3. Otherwise the request status is used.
        """
        if status_code in self.TERMINAL_STATUS_CODES:
            return self.lookup_state(status_code, direction, request_type)

        has_local = local_status_code not in ("", "0")
        if has_local: # TODO: and status_code in self.POST_DELIVERY_STATUS_CODES: check with real data
            local_mapped = self.lookup_local_state(
                local_status_code, direction, request_type
            )
            if local_mapped is not None:
                return local_mapped
            # Unknown local code: fall back to the request status, but do
            # not claim confidence about a state we could not interpret.
            mapped = self.lookup_state(status_code, direction, request_type)
            return StatusMapping(mapped.state, False) if mapped else None

        return self.lookup_state(status_code, direction, request_type)

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
        local_status = LocalStatus(
            status=str(record.get("local_status") or ""),
            code=str(record.get("local_status_code") or "0"),
        )

        # Keep the Libris request status as the provider status; the local
        # status is preserved separately on `local_status`.
        status_code = str(record.get("status_code") or "")
        status_text = record.get("status")

        mapped = self.resolve_state(
            status_code,
            local_status.code,
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
            schema_version=self.schema_version,
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
            receiving_library=(
                ReceivingLibrary(
                    library_code=str(record["receiving_library"]["library_code"]),
                    name=str(record["receiving_library"]["name"]),
                    department=str(record["receiving_library"].get("department") or ""),
                    address1=str(record["receiving_library"].get("address1") or ""),
                    address2=str(record["receiving_library"].get("address2") or ""),
                    address3=str(record["receiving_library"].get("address3") or ""),
                    zip_code=str(record["receiving_library"].get("zip_code") or ""),
                    city=str(record["receiving_library"].get("city") or ""),
                    fax=str(record["receiving_library"].get("fax") or ""),
                    email=str(record["receiving_library"].get("email") or ""),
                    bibsam=bool(record["receiving_library"].get("bibsam") or False),
                )
                if record.get("receiving_library")
                else None
            ),
            recipients=[
                RequestParty(
                    library_id=str(recipient.get("library_id")),
                    library_code=str(recipient.get("library_code")),
                    is_active_library=bool(recipient.get("is_active_library") or False),
                    location=str(recipient.get("location") or ""),
                    response_id=str(recipient.get("response_id") or ""),
                    response=str(recipient.get("response") or ""),
                    response_date=(
                        datetime.fromisoformat(recipient["response_date"])
                        if recipient.get("response_date")
                        else None
                    ),
                    reserve=bool(recipient.get("reserve") or False),
                )
                for recipient in record.get("recipients", [])
            ],
            local_status=local_status,
            bibliographic=self._bibliographic(record),
            provider_status_raw=status_text,
            provider_status_code=status_code or None,
            provider_revision=provider_revision,
            observed_at=observed_at,
            extensions=self.extract_extensions(record),
            mapped_state=mapped.state if mapped else None,
            mapping_confident=mapped.confident if mapped else False,
            event_key=event_key,
            correlation_id=correlation_id or uuid4(),
        )
