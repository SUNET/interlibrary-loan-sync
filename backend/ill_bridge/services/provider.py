from uuid import UUID

from ill_bridge.domain.enums import AdapterKeyType
from ill_bridge.db.models.provider import Provider
from ill_bridge.repositories.provider import ProviderRepository


class ProviderService:

    def __init__(
        self,
        repository: ProviderRepository,
    ):
        self.repository = repository

    async def enable_provider(
        self,
        tenant_id: UUID,
        provider_id: UUID,
    ) -> Provider:

        provider = await self.repository.get_for_tenant(
            tenant_id,
            provider_id,
        )

        if provider is None:
            raise ProviderNotFoundError()

        if provider.adapter_key == AdapterKeyType.LIBRIS:
            # Business rule:
            # enabling a Libris provider does not automatically
            # enable writes.
            provider.writes_enabled = False

        provider.enabled = True

        return provider