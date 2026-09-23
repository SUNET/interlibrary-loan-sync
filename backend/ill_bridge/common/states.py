from __future__ import annotations

from enum import StrEnum


class State(StrEnum):
    """Marker base for all lifecycle / processing states."""

    pass


class WorkflowState(State):
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    ON_HOLD = "ON_HOLD"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED = "RECEIVED"
    READY_FOR_PICKUP = "READY_FOR_PICKUP"
    ON_LOAN = "ON_LOAN"
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
