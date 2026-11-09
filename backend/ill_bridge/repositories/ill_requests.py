from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.models import IllRequests


class IllRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, limit: int = 100) -> list[IllRequests]:
        result = await self._session.execute(
            select(IllRequests)
            .order_by(desc(IllRequests.updated_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, request_id: UUID) -> IllRequests | None:
        result = await self._session.execute(
            select(IllRequests).where(IllRequests.id == request_id)
        )
        return result.scalar_one_or_none()
