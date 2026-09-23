from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.common.exceptions import ProviderNotFound
from ill_bridge.database.models import Providers


@dataclass(frozen=True)
class ProviderRef:
    """Credential-free provider data used by cross-tenant schedulers."""

    id: UUID
    tenant_id: UUID
    adapter_key: str
    local_library_code: str
    poll_interval_seconds: int


class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[Providers]:
        """Retrieve all providers across all tenants, ordered by display name."""
        result = await self._session.execute(
            select(Providers).order_by(Providers.display_name)
        )
        return list(result.scalars().all())

    async def get_by_id(self, provider_id: UUID) -> Providers | None:
        """Retrieve a single provider by its primary ID, ignoring tenant boundaries."""
        result = await self._session.execute(
            select(Providers).where(Providers.id == provider_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_tenant(
        self, tenant_id: UUID, provider_id: UUID
    ) -> Providers | None:
        """Retrieve a single provider ensuring it belongs to the specified tenant."""
        result = await self._session.execute(
            select(Providers).where(
                Providers.id == provider_id,
                Providers.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_required_for_tenant(
        self, tenant_id: UUID, provider_id: UUID
    ) -> Providers:
        """Retrieve a provider for a tenant, raising ProviderNotFound if it doesn't exist."""
        provider = await self.get_by_id_for_tenant(tenant_id, provider_id)
        if provider is None:
            raise ProviderNotFound(
                f"Provider {provider_id} not found for tenant {tenant_id}"
            )
        return provider

    async def list_for_tenant(self, tenant_id: UUID) -> list[Providers]:
        """Retrieve all providers configured for a specific tenant."""
        result = await self._session.execute(
            select(Providers)
            .where(Providers.tenant_id == tenant_id)
            .order_by(Providers.display_name)
        )
        return list(result.scalars().all())

    async def list_enabled_refs(self) -> list[ProviderRef]:
        """Retrieve lightweight reference objects for all globally enabled providers (for schedulers)."""
        result = await self._session.execute(
            select(
                Providers.id,
                Providers.tenant_id,
                Providers.adapter_key,
                Providers.local_library_code,
                Providers.poll_interval_seconds,
            ).where(Providers.enabled.is_(True))
        )
        return [ProviderRef(*row) for row in result.all()]

    async def create(self, provider: Providers) -> Providers:
        """Persist a new provider record."""
        self._session.add(provider)
        await self._session.flush()
        return provider

    async def delete(self, provider: Providers) -> None:
        """Delete an existing provider record."""
        await self._session.delete(provider)
        await self._session.flush()
