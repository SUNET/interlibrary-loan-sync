from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.models import RequestParties


class RequestPartyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, limit: int = 100) -> list[RequestParties]:
        result = await self._session.execute(
            select(RequestParties)
            .order_by(RequestParties.ill_request_id, RequestParties.ordinal)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, party_id: UUID) -> RequestParties | None:
        result = await self._session.execute(
            select(RequestParties).where(RequestParties.id == party_id)
        )
        return result.scalar_one_or_none()
