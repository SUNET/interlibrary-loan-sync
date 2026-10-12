# ill_bridge/providers/registry.py
from dataclasses import dataclass

from ill_bridge.common.enums import AdapterKeyType, ILLDirection
from ill_bridge.common.exceptions import UnknownAdapter
from ill_bridge.common.secrets import SecretResolverPassbolt
from ill_bridge.database.models import Providers as ProviderDbModel
from ill_bridge.providers.base import IllProvider

# from ill_bridge.providers.fake.adapter import FakeAdapter
from ill_bridge.providers.libris.adapter import LibrisAdapter
from ill_bridge.providers.loader import MappingLoader


@dataclass(frozen=True, slots=True)
class AdapterSpec:
    key: str
    adapter: type[IllProvider]
    feeds: tuple[str, ...]


_ADAPTERS: dict[AdapterKeyType, AdapterSpec] = {
    AdapterKeyType.LIBRIS: AdapterSpec(
        key="libris",
        adapter=LibrisAdapter,
        feeds=LibrisAdapter.feeds,
    ),
    # AdapterKeyType.FAKE: AdapterSpec(
    #     key="fake",
    #     adapter=FakeAdapter,
    #     feeds=FakeAdapter.feeds,
    # ),
}


class ProviderRegistry:
    def __init__(
        self,
        *,
        secret_resolver: SecretResolverPassbolt,
        mapping_loader: MappingLoader,
    ):
        self._secrets = secret_resolver
        self._mappings = mapping_loader

    def spec_for(self, adapter_key: str) -> AdapterSpec:
        try:
            return _ADAPTERS[adapter_key]
        except KeyError:
            raise UnknownAdapter(adapter_key)

    def feeds_for(
        self, adapter_key: str, direction: ILLDirection, from_archive=False, days: int = 30
    ) -> tuple[str, ...]:
        spec = self.spec_for(adapter_key)

        if from_archive:
            return spec.adapter.archive(direction=direction, days=days)

        if direction == ILLDirection.LENDING:
            return spec.adapter.lending_feeds
        elif direction == ILLDirection.BORROWING:
            return spec.adapter.borrowing_feeds
        else:
            return spec.feeds

    def create(self, row: ProviderDbModel) -> IllProvider:
        spec = self.spec_for(row.adapter_key)

        return spec.adapter(
            sigel=row.local_library_code,
            base_url=row.base_url,
            api_key=self._secrets.resolve(row.secret_ref),
            mapping=self._mappings.load(row.mapping_version),
            writes_enabled=row.writes_enabled,
        )
