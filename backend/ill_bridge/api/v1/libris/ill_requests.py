from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.ill_requests import IllRequestRepository
from ill_bridge.schemas.response.libris import IllRequestRead
from ill_bridge.services.ill_requests import IllRequestService

router = APIRouter()


def get_ill_request_service(
    session: AsyncSession = Depends(get_db),
) -> IllRequestService:
    return IllRequestService(IllRequestRepository(session))


@router.get("/ill_requests", response_model=list[IllRequestRead])
async def list_ill_requests(
    limit: int = 100,
    service: IllRequestService = Depends(get_ill_request_service),
) -> list[IllRequestRead]:
    rows = await service.list_ill_requests(limit=limit)
    return [IllRequestRead.model_validate(row) for row in rows]


@router.get("/ill_requests/{id}", response_model=IllRequestRead)
async def get_ill_request(
    id: UUID,
    service: IllRequestService = Depends(get_ill_request_service),
) -> IllRequestRead:
    row = await service.get_ill_request(id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ILL request not found",
        )
    return IllRequestRead.model_validate(row)
