class ProviderDisabledError(Exception):
    pass


class ProviderWriteDisabledError(Exception):
    pass


class JobNotFoundError(LookupError):
    """Raised when an operation targets a job id that does not exist."""


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


class MappingProfileNotFound(LookupError):
    """Raised when a mapping profile is not found for a given version."""

    def __init__(self, version: str):
        super().__init__(f"Mapping profile not found for version: {version}")
        self.version = version
