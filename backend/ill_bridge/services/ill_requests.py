from __future__ import annotations

from uuid import UUID

from ill_bridge.database.models import IllRequests
from ill_bridge.repositories.ill_requests import IllRequestRepository


class IllRequestService:
    def __init__(self, repository: IllRequestRepository) -> None:
        self.repository = repository

    async def list_ill_requests(self, limit: int = 100) -> list[IllRequests]:
        return await self.repository.list_all(limit=limit)

    async def get_ill_request(self, request_id: UUID) -> IllRequests | None:
        return await self.repository.get_by_id(request_id)
