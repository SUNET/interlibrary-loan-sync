from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.effect_queue import EffectQueueRepository
from ill_bridge.schemas.response.libris import EffectQueueRead
from ill_bridge.services.effect_queue import EffectQueueService

router = APIRouter()


def get_effect_queue_service(
    session: AsyncSession = Depends(get_db),
) -> EffectQueueService:
    return EffectQueueService(EffectQueueRepository(session))


@router.get("/effect_queue", response_model=list[EffectQueueRead])
async def list_effect_queue(
    limit: int = 100,
    service: EffectQueueService = Depends(get_effect_queue_service),
) -> list[EffectQueueRead]:
    rows = await service.list_effects(limit=limit)
    return [EffectQueueRead.model_validate(row) for row in rows]


@router.get("/effect_queue/{id}", response_model=EffectQueueRead)
async def get_effect_queue(
    id: UUID,
    service: EffectQueueService = Depends(get_effect_queue_service),
) -> EffectQueueRead:
    row = await service.get_effect(id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Effect queue entry not found",
        )
    return EffectQueueRead.model_validate(row)
