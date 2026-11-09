from __future__ import annotations

from uuid import UUID, uuid4

from ill_bridge.database.models import Tenants
from ill_bridge.repositories.tenant import TenantRepository
from ill_bridge.schemas.request.tenant import TenantCreate


class TenantService:
    def __init__(self, repository: TenantRepository) -> None:
        self.repository = repository

    async def list_tenants(self) -> list[Tenants]:
        return await self.repository.list_all()

    async def get_tenant(self, tenant_id: UUID) -> Tenants | None:
        return await self.repository.get_by_id(tenant_id)

    async def create_tenant(self, payload: TenantCreate) -> Tenants:
        tenant = Tenants(
            id=uuid4(),
            folio_tenant_key=payload.folio_tenant_key,
            name=payload.name,
            infodisk_email=payload.infodisk_email,
        )
        return await self.repository.create(tenant)
