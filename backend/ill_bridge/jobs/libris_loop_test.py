from ill_bridge.common.secrets import SecretResolverPassbolt
from ill_bridge.config import Settings
from ill_bridge.database.session import make_engine, make_sessionmaker
from ill_bridge.providers.loader import MappingLoader
from ill_bridge.providers.registry import ProviderRegistry
from ill_bridge.repositories.provider import ProviderRepository


async def test_provider_repository():
    settings = Settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    async with sessionmaker() as session:
        provider_repo = ProviderRepository(session)
        registry = ProviderRegistry(
            secret_resolver=SecretResolverPassbolt,
            mapping_loader=MappingLoader,
        )
        providers = await provider_repo.list_all()
        for provider in providers:
            sp_provider = await provider_repo.get_required_for_tenant(provider.tenant_id, provider.id)
            feeds = registry.feeds_for(sp_provider.adapter_key)
            adapter = registry.create(sp_provider)
            print(f"Provider{{Name: {sp_provider.display_name}, Sigel: {sp_provider.local_library_code}, Adapter Key: {sp_provider.adapter_key}, Mapping Version: {sp_provider.mapping_version}}}")
            print(f"\tFeeds: {feeds}")
            for feed in feeds:
                print(f"\t\tFeed: {feed} -> Adapter: {adapter}")
                request = await adapter.fetch_requests(feed=feed)
                print(f"\t\t\tRequest Count: {request.count}")
                break  # Remove this break to fetch all feeds for each provider
                
                # print(f"\t\t\tSpecific Provider: {sp_provider}")


if __name__ == "__main__":
    # secretspec run -- uv run python -m ill_bridge.jobs.libris_loop_test
    import asyncio

    asyncio.run(test_provider_repository())
    