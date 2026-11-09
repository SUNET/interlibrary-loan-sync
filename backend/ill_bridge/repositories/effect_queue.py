from __future__ import annotations

from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.models import EffectQueue


class EffectQueueRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, limit: int = 100) -> list[EffectQueue]:
        result = await self._session.execute(
            select(EffectQueue)
            .order_by(desc(EffectQueue.available_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_id(self, effect_id: UUID) -> EffectQueue | None:
        result = await self._session.execute(
            select(EffectQueue).where(EffectQueue.id == effect_id)
        )
        return result.scalar_one_or_none()
