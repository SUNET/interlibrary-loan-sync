from __future__ import annotations

from uuid import UUID, uuid4

from ill_bridge.common.enums import AdapterKeyType
from ill_bridge.common.exceptions import ProviderNotFound
from ill_bridge.database.models import Providers
from ill_bridge.repositories.provider import ProviderRepository
from ill_bridge.schemas.request.provider import ProviderCreate


class ProviderService:
    def __init__(self, repository: ProviderRepository) -> None:
        self.repository = repository

    async def list_providers(self) -> list[Providers]:
        return await self.repository.list_all()

    async def get_provider(self, provider_id: UUID) -> Providers | None:
        return await self.repository.get_by_id(provider_id)

    async def create_provider(self, payload: ProviderCreate) -> Providers:
        provider = Providers(
            id=uuid4(),
            tenant_id=payload.tenant_id,
            adapter_key=payload.adapter_key,
            account_key=payload.account_key,
            display_name=payload.display_name,
            local_library_scheme=payload.local_library_scheme,
            local_library_code=payload.local_library_code,
            base_url=payload.base_url,
            secret_ref=payload.secret_ref,
            enabled=payload.enabled,
            writes_enabled=payload.writes_enabled,
            mapping_version=payload.mapping_version,
            poll_interval_seconds=payload.poll_interval_seconds,
            capabilities=payload.capabilities,
            config=payload.config,
        )
        return await self.repository.create(provider)

    async def enable_provider(
        self,
        tenant_id: UUID,
        provider_id: UUID,
    ) -> Providers:
        provider = await self.repository.get_by_id_for_tenant(
            tenant_id,
            provider_id,
        )

        if provider is None:
            raise ProviderNotFound(
                f"Provider {provider_id} not found for tenant {tenant_id}"
            )

        if provider.adapter_key == AdapterKeyType.LIBRIS:
            # Business rule:
            # enabling a Libris provider does not automatically
            # enable writes.
            provider.writes_enabled = False

        provider.enabled = True

        return provider
