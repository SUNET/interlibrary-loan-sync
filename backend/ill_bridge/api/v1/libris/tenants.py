from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.tenant import TenantRepository
from ill_bridge.schemas.request.tenant import TenantCreate, TenantRead
from ill_bridge.services.tenant import TenantService

router = APIRouter()


def get_tenant_service(
    session: AsyncSession = Depends(get_db),
) -> TenantService:
    return TenantService(TenantRepository(session))


@router.get("/tenants", response_model=list[TenantRead])
async def list_tenants(
    service: TenantService = Depends(get_tenant_service),
) -> list[TenantRead]:
    tenants = await service.list_tenants()
    return [TenantRead.model_validate(tenant) for tenant in tenants]


@router.get("/tenants/{id}", response_model=TenantRead)
async def get_tenant(
    id: UUID,
    service: TenantService = Depends(get_tenant_service),
) -> TenantRead:
    tenant = await service.get_tenant(id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantRead.model_validate(tenant)


@router.post(
    "/tenants",
    response_model=TenantRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant(
    payload: TenantCreate,
    session: AsyncSession = Depends(get_db),
    service: TenantService = Depends(get_tenant_service),
) -> TenantRead:
    tenant = await service.create_tenant(payload)
    await session.commit()
    return TenantRead.model_validate(tenant)
