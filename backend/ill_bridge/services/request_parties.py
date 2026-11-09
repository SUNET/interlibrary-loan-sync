from __future__ import annotations

from uuid import UUID

from ill_bridge.database.models import RequestParties
from ill_bridge.repositories.request_parties import RequestPartyRepository


class RequestPartyService:
    def __init__(self, repository: RequestPartyRepository) -> None:
        self.repository = repository

    async def list_request_parties(self, limit: int = 100) -> list[RequestParties]:
        return await self.repository.list_all(limit=limit)

    async def get_request_party(self, party_id: UUID) -> RequestParties | None:
        return await self.repository.get_by_id(party_id)
