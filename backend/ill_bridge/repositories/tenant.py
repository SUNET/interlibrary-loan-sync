from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.models import Tenants


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Tenants]:
        result = await self._session.execute(
            select(Tenants).order_by(Tenants.name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, tenant_id: UUID) -> Tenants | None:
        result = await self._session.execute(
            select(Tenants).where(Tenants.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def create(self, tenant: Tenants) -> Tenants:
        self._session.add(tenant)
        await self._session.flush()
        await self._session.refresh(tenant)
        return tenant
