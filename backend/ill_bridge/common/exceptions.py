from __future__ import annotations

from uuid import UUID


class ProviderDisabledError(Exception):
    pass


class ProviderWriteDisabledError(Exception):
    pass


class JobNotFoundError(LookupError):
    """Raised when an operation targets a job id that does not exist."""


class InvalidJobStatus(ValueError):
    """Raised when a job status filter is not a known Procrastinate status."""


class InvalidWorkflowTransition(Exception):
    """Raised when a workflow transition is attempted that is not allowed."""


class UnknownAdapter(RuntimeError):
    def __init__(self, adapter_key: str):
        super().__init__(f"Unknown adapter key: {adapter_key}")
        self.adapter_key = adapter_key


class UnsupportedCapability(RuntimeError):
    def __init__(self, capability: str):
        super().__init__(f"Unsupported capability: {capability}")
        self.capability = capability


class SecretResolutionError(RuntimeError):
    """Raised when a secret reference cannot be resolved to a value."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnknownLibrisMediaType(ValueError):
    """Raised when Libris returns an unsupported media type code."""


class InvalidLibrisRecord(ValueError):
    """Raised when a Libris record is missing required fields."""


class ProviderNotFound(LookupError):
    """Raised when a provider is not found for a given tenant and provider id."""


class BorrowingOrderNotFound(LookupError):
    """Raised when a borrowing order is not found for a given tenant and id."""


class TenantMismatch(RuntimeError):
    """Raised when a row exists but does not belong to the acting tenant.

    Distinct from "not found": the identifier is real, so retrying or
    creating is wrong. Usually means ``app.tenant_id`` disagrees with the
    tenant the caller passed, or a caller-supplied id belongs elsewhere.
    """


class LibrisReferenceInUse(RuntimeError):
    """Raised when an lf_number is already claimed by another order.

    At most one order may claim a Libris reference per tenant, enforced by
    the partial unique index ``borrowing_orders_lf_number_uq``. Two orders
    claiming one Libris request would make the A6 link ambiguous.
    """

    def __init__(self, lf_number: str, order_id: UUID | None = None) -> None:
        super().__init__(
            f"Libris reference {lf_number!r} is already claimed"
            + (f" by order {order_id}" if order_id else "")
        )
        self.lf_number = lf_number
        self.order_id = order_id


class MappingProfileNotFound(LookupError):
    """Raised when a mapping profile is not found for a given version."""

    def __init__(self, version: str):
        super().__init__(f"Mapping profile not found for version: {version}")
        self.version = version


class StaleVersionError(RuntimeError):
    """Raised when an operation is attempted on a stale version of a record."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class FolioTenantConfigNotFoundError(LookupError):
    """Raised when a FOLIO tenant configuration is not found for a given tenant key."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
