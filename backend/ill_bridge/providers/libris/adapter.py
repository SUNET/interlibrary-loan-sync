from typing import ClassVar

from ill_bridge.common.api import AsyncApiClient
from ill_bridge.common.enums import (
    ILLDirection,
    LibrisFeed,
    ProviderCommand,
    RequestType,
)
from ill_bridge.common.models import (
    ProviderCapabilities,
    ProviderRequestObservation,
    ProviderRequests,
)


class LibrisAdapter:
    feeds: ClassVar[tuple[str, ...]] = tuple(feed.value for feed in LibrisFeed)
    capabilities: ClassVar = ProviderCapabilities(
        directions=frozenset({ILLDirection.BORROWING, ILLDirection.LENDING}),
        request_types=frozenset({RequestType.LOAN, RequestType.COPY}),
        commands=frozenset({ProviderCommand.PROVIDER_ACCEPT, ProviderCommand.PROVIDER_REJECT, ProviderCommand.PROVIDER_CANCEL}),
        supports_webhooks=False,
        supports_cursors=False,
        native_idempotency=False,
    )

    def __init__(self, *, sigel, base_url, api_key, mapping, writes_enabled):
        self.sigel = sigel
        self.mapping = mapping
        self.base_url = base_url
        self.writes_enabled = writes_enabled
        self._http = AsyncApiClient(
            base_url=base_url.rstrip("/"),
            headers={"api-key": api_key},
            timeout=10.0,
        )

    @property
    def is_writable(self) -> bool:
        return self.writes_enabled

    async def fetch_requests(self, *, feed: str) -> ProviderRequests:
        payload: dict = await self._http.get(f"/illrequests/{self.sigel}/{feed}")
        return ProviderRequests(
            feed=feed,
            count=int(payload.get("count", 0)),
            requests=payload.get("ill_requests", []),
        )

    def normalize(self, record, *, observed_at) -> ProviderRequestObservation:
        return self.mapping.normalize(
            record, our_sigel=self.sigel, observed_at=observed_at
        )
        
    def __repr__(self):
        return f"<LibrisAdapter sigel={self.sigel} base_url={self.base_url} mapping_version={self.mapping.version}>"
