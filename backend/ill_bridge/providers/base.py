from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from ill_bridge.common.models import (
    ProviderCapabilities,
    ProviderRequestObservation,
    ProviderRequests,
)


class IllProvider(Protocol):
    sigel: str
    writes_enabled: bool
    feeds: tuple[str, ...]
    lending_feeds: tuple[str, ...]
    borrowing_feeds: tuple[str, ...]
    capabilities: ProviderCapabilities

    @property
    def is_writable(self) -> bool:
        pass

    async def fetch_requests(self, *, feed: str) -> ProviderRequests:
        pass

    def normalize(
        self, record: dict, *, observed_at: datetime
    ) -> ProviderRequestObservation:
        pass


class MappingProfile(Protocol):
    version: str

    def normalize(
        self,
        record: Mapping[str, Any],
        *,
        our_sigel: str,
        observed_at: datetime,
    ) -> ProviderRequestObservation:
        pass
