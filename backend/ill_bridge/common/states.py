from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    """Marker base for all lifecycle / processing states."""

    pass


class WorkflowState(State):
    REQUESTED = "REQUESTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESERVED = "RESERVED"
    DELIVERED = "DELIVERED"
    RENEWAL_REQUESTED = "RENEWAL_REQUESTED"
    RENEWAL_ACKNOWLEDGED = "RENEWAL_ACKNOWLEDGED"
    ACCEPTED = "ACCEPTED"
    ON_HOLD = "ON_HOLD"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"
    RECEIVED = "RECEIVED"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    ON_LOAN = "ON_LOAN"
    RETURNED_FROM_PATRON = "RETURNED_FROM_PATRON"
    RETURN_PENDING = "RETURN_PENDING"
    RETURN_IN_TRANSIT = "RETURN_IN_TRANSIT"
    RETURNED = "RETURNED"
    FULFILLED = "FULFILLED"
    COMPLETED = "COMPLETED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ProcessingState(State):
    PENDING = "PENDING"
    IN_SYNC = "IN_SYNC"
    RETRYING = "RETRYING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    CONFLICT = "CONFLICT"
    PAUSED = "PAUSED"


class BorrowingOrderProcessingState(State):
    """Whether the effects owed by an order have completed.

    Deliberately not :class:`ProcessingState`: an order owes one effect, the
    infodisk mail, so it is either handled or it is not. Why it is unhandled
    lives on the ``effect_queue`` row (``attempts``, ``last_error``).
    """

    UNHANDLED = "UNHANDLED"
    HANDLED = "HANDLED"


class BorrowingOrderState(State):
    """Local lifecycle of an A5 order, before Libris knows it exists."""

    SUBMITTED = "SUBMITTED"  # saved, infodisk mail queued
    LINKED = "LINKED"  # at least one Libris request linked; NOT terminal
    CANCELLED = "CANCELLED"  # cancelled before Libris; terminal


class FolioUserStatus(State):
    """Outcome of the FOLIO patron check at intake.

    ``CHECK_FAILED`` exists so a FOLIO outage is not recorded as
    ``NOT_FOUND``: the infodisk mail would otherwise tell staff the patron
    does not exist when we simply could not ask. It also covers the
    unexpected case of a barcode matching more than one FOLIO user, which
    must never resolve by picking the first hit.
    """

    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    CHECK_FAILED = "CHECK_FAILED"
