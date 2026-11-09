from __future__ import annotations

from uuid import UUID

from ill_bridge.database.models import EffectQueue
from ill_bridge.repositories.effect_queue import EffectQueueRepository


class EffectQueueService:
    def __init__(self, repository: EffectQueueRepository) -> None:
        self.repository = repository

    async def list_effects(self, limit: int = 100) -> list[EffectQueue]:
        return await self.repository.list_all(limit=limit)

    async def get_effect(self, effect_id: UUID) -> EffectQueue | None:
        return await self.repository.get_by_id(effect_id)
