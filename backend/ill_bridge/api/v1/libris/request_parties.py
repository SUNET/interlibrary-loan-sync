from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.request_parties import RequestPartyRepository
from ill_bridge.schemas.response.libris import RequestPartyRead
from ill_bridge.services.request_parties import RequestPartyService

router = APIRouter()


def get_request_party_service(
    session: AsyncSession = Depends(get_db),
) -> RequestPartyService:
    return RequestPartyService(RequestPartyRepository(session))


@router.get("/request_parties", response_model=list[RequestPartyRead])
async def list_request_parties(
    limit: int = 100,
    service: RequestPartyService = Depends(get_request_party_service),
) -> list[RequestPartyRead]:
    rows = await service.list_request_parties(limit=limit)
    return [RequestPartyRead.model_validate(row) for row in rows]


@router.get("/request_parties/{id}", response_model=RequestPartyRead)
async def get_request_party(
    id: UUID,
    service: RequestPartyService = Depends(get_request_party_service),
) -> RequestPartyRead:
    row = await service.get_request_party(id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request party not found",
        )
    return RequestPartyRead.model_validate(row)
