from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from ill_bridge.database.session import get_db
from ill_bridge.repositories.provider import ProviderRepository
from ill_bridge.schemas.request.provider import ProviderCreate, ProviderRead
from ill_bridge.services.provider import ProviderService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


def get_provider_service(
    session: AsyncSession = Depends(get_db),
) -> ProviderService:
    return ProviderService(ProviderRepository(session))


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(
    service: ProviderService = Depends(get_provider_service),
) -> list[ProviderRead]:
    providers = await service.list_providers()
    return [ProviderRead.model_validate(provider) for provider in providers]


@router.get("/providers/{id}", response_model=ProviderRead)
async def get_provider(
    id: UUID,
    service: ProviderService = Depends(get_provider_service),
) -> ProviderRead:
    provider = await service.get_provider(id)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Provider not found",
        )
    return ProviderRead.model_validate(provider)


@router.post(
    "/providers",
    response_model=ProviderRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider(
    payload: ProviderCreate,
    session: AsyncSession = Depends(get_db),
    service: ProviderService = Depends(get_provider_service),
) -> ProviderRead:
    provider = await service.create_provider(payload)
    await session.commit()
    return ProviderRead.model_validate(provider)
