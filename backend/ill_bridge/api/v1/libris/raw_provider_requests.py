from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.raw_provider_requests import RawProviderRequestRepository
from ill_bridge.schemas.response.libris import RawProviderRequestRead
from ill_bridge.services.raw_provider_requests import RawProviderRequestService

router = APIRouter()


def get_raw_provider_request_service(
    session: AsyncSession = Depends(get_db),
) -> RawProviderRequestService:
    return RawProviderRequestService(RawProviderRequestRepository(session))


@router.get("/raw_provider_requests", response_model=list[RawProviderRequestRead])
async def list_raw_provider_requests(
    limit: int = 100,
    service: RawProviderRequestService = Depends(get_raw_provider_request_service),
) -> list[RawProviderRequestRead]:
    rows = await service.list_raw_provider_requests(limit=limit)
    return [RawProviderRequestRead.model_validate(row) for row in rows]


@router.get("/raw_provider_requests/{id}", response_model=RawProviderRequestRead)
async def get_raw_provider_request(
    id: UUID,
    service: RawProviderRequestService = Depends(get_raw_provider_request_service),
) -> RawProviderRequestRead:
    row = await service.get_raw_provider_request(id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Raw provider request not found",
        )
    return RawProviderRequestRead.model_validate(row)
