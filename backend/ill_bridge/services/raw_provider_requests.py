from __future__ import annotations

from uuid import UUID

from ill_bridge.database.models import RawProviderRequests
from ill_bridge.repositories.raw_provider_requests import RawProviderRequestRepository


class RawProviderRequestService:
    def __init__(self, repository: RawProviderRequestRepository) -> None:
        self.repository = repository

    async def list_raw_provider_requests(
        self, limit: int = 100
    ) -> list[RawProviderRequests]:
        return await self.repository.list_all(limit=limit)

    async def get_raw_provider_request(
        self, record_id: UUID
    ) -> RawProviderRequests | None:
        return await self.repository.get_by_id(record_id)
