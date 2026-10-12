from __future__ import annotations

from enum import StrEnum


class ProviderCommand(StrEnum):
    PROVIDER_ACCEPT = "PROVIDER_ACCEPT"
    PROVIDER_REJECT = "PROVIDER_REJECT"
    PROVIDER_CANCEL = "PROVIDER_CANCEL"
    PROVIDER_REVIEW_NEW_REQUEST = "PROVIDER_REVIEW_NEW_REQUEST"

class EvidenceSource(StrEnum):
    PROVIDER = "PROVIDER"  # Libris said so
    FOLIO_CIRCULATION = "FOLIO_CIRCULATION"  # a real circulation event
    STAFF = "STAFF"  # an authorised human
    SYSTEM = "SYSTEM"  # our own scheduler


class AdapterKeyType(StrEnum):
    LIBRIS = "libris"
    FAKE = "fake"
    RAPIDILL = "rapidill"


class LocalLibraryScheme(StrEnum):
    SIGEL = "SIGEL"


class ILLDirection(StrEnum):
    BORROWING = "BORROWING"  # inlån — we ask another library
    LENDING = "LENDING"  # utlån — another library asks us


class RequestType(StrEnum):
    LOAN = "LOAN"  # lån
    COPY = "COPY"  # kopia


class ILLRequestStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"


class LibrisFeed(StrEnum):
    # ---- Lending ----
    INCOMING = "incoming"
    RECENT = "recent"
    RESERVATIONS = "reservations"
    CANCELLATIONS = "cancellations"

    # ---- Borrowing ----
    INBOX = "inbox"
    MAY_RESERVE = "may_reserve"
    NOT_FULFILLED = "notfullfilled"
    DELIVERED = "delivered"
    LAST = "last"

    # ------------------------------------------------------------------
    # Convenience grouping
    # ------------------------------------------------------------------

    @property
    def direction(self) -> ILLDirection:
        if self in self.lending():
            return ILLDirection.LENDING
        return ILLDirection.BORROWING

    @classmethod
    def lending(cls) -> tuple[LibrisFeed, ...]:
        return (
            cls.INCOMING,
            cls.RECENT,
            cls.RESERVATIONS,
            cls.CANCELLATIONS,
        )

    @classmethod
    def borrowing(cls) -> tuple[LibrisFeed, ...]:
        return (
            cls.INBOX,
            cls.MAY_RESERVE,
            cls.NOT_FULFILLED,
            cls.DELIVERED,
            cls.LAST,
        )

    @classmethod
    def all(cls) -> list[str]:
        # [feed.value for feed in LibrisFeed] = [feed.value for feed in cls]
        return cls.lending() + cls.borrowing()
        
