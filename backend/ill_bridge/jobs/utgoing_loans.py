import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rich.logging import RichHandler

from ill_bridge.common.enums import ILLDirection
from ill_bridge.common.exceptions import InvalidWorkflowTransition
from ill_bridge.common.folio_client import (
    get_folio_client,
)
from ill_bridge.common.models import (
    ProviderRequestObservation,
    ProviderRequests,
)
from ill_bridge.common.secrets import SecretResolverPassbolt
from ill_bridge.common.states import ProcessingState, WorkflowState
from ill_bridge.common.transitions import Workflow
from ill_bridge.config import Settings
from ill_bridge.database.models import Providers as ProviderDbModel
from ill_bridge.database.session import make_engine, make_sessionmaker
from ill_bridge.providers.base import IllProvider
from ill_bridge.providers.loader import MappingLoader
from ill_bridge.providers.registry import ProviderRegistry
from ill_bridge.repositories.provider_polling import ProviderPollingRepository

POLL_INTERVAL_SECONDS = 45.0
DAYS = 1
LOG_PATH = Path("logs/libris_loop.log")
logger = logging.getLogger(__name__)
folio_client = get_folio_client()


def configure_logging() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            RichHandler(rich_tracebacks=True),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ],
        force=True,
    )


async def wait_for_next_poll(duration: float = POLL_INTERVAL_SECONDS) -> None:
    logger.info("next poll begins in %.0f seconds", duration)
    await asyncio.sleep(duration)


async def record_raw_provider_event(
    repository: ProviderPollingRepository,
    *,
    tenant_id,
    provider_id,
    source_key: str,
    event_key: str,
    payload: dict,
) -> bool:
    return await repository.record_raw_provider_event(
        tenant_id=tenant_id,
        provider_id=provider_id,
        source_key=source_key,
        event_key=event_key,
        payload=payload,
    )


async def poll_enabled_providers() -> None:
    settings = Settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    try:
        async with sessionmaker() as session:
            repository = ProviderPollingRepository(session)
            registry = ProviderRegistry(
                secret_resolver=SecretResolverPassbolt,
                mapping_loader=MappingLoader,
            )
            provider_refs = await repository.list_enabled_providers()
            logger.info("polling %d enabled provider(s)", len(provider_refs))
            logger.info("polling enabled providers: %s", provider_refs)

            for provider_ref in provider_refs:
                # tenant: Tenants = await repository.get_tenant(provider_ref.tenant_id)
                provider: ProviderDbModel = (
                    await repository.get_required_provider_for_tenant(
                        provider_ref.tenant_id, provider_ref.id
                    )
                )
                adapter: IllProvider = registry.create(provider)
                logger.info(
                    "feeds: %s",
                    registry.feeds_for(provider.adapter_key, ILLDirection.LENDING),
                )

                for feed in registry.feeds_for(
                    provider.adapter_key,
                    ILLDirection.LENDING,
                    from_archive=True,
                    days=DAYS,
                ):
                    page: ProviderRequests = await adapter.fetch_requests(feed=feed)
                    logger.info(
                        "===> fetched %d requests from %s/%s",
                        page.count,
                        provider.display_name,
                        feed,
                    )
                    logger.info("processing incoming feed: %s \nreq: %s", feed, page)
                    new_events = 0
                    for record in page.requests:
                        # if feed == LibrisFeed.INCOMING.value and page.count > 0:
                        logger.info("processing incoming record: %s", record)

                        event_key = (
                            f"{record.get('lf_number')}:{record.get('last_modified')}"
                            if record.get("last_modified")
                            else record.get("lf_number")
                        )
                        logger.info("===> event_key: %s", event_key)
                        if not event_key:
                            logger.warning(
                                "skipping record without an event key from %s/%s",
                                provider.display_name,
                                feed,
                            )
                            continue

                        inserted = await record_raw_provider_event(
                            repository,
                            tenant_id=provider.tenant_id,
                            provider_id=provider.id,
                            source_key=feed,
                            event_key=event_key,
                            payload=record,
                        )
                        # A duplicate raw event only means the payload was already
                        # archived; downstream processing must still run so that
                        # failed/incomplete syncs and effects can be retried.
                        if inserted:
                            new_events += 1
                            logger.info(
                                "recorded new raw provider event: %s", event_key
                            )
                        else:
                            logger.info(
                                "raw provider event already recorded, continuing processing: %s",
                                event_key,
                            )

                        observation: ProviderRequestObservation = adapter.normalize(
                            record, observed_at=datetime.now(timezone.utc)
                        )

                        logger.info(
                            "===> normalized observation: %s",
                            observation,
                        )
                        logger.info(
                            "===> receiving_library: %s",
                            record.get("receiving_library"),
                        )

                        current = await repository.get_ill_request_by_provider_external_identity(
                            tenant_id=provider.tenant_id,
                            provider_id=provider.id,
                            observation=observation,
                        )
                        from_state = (
                            WorkflowState(current.workflow_state)
                            if current and current.workflow_state
                            else None
                        )
                        logger.info(
                            "===> current: %s, from_state: %s", current, from_state
                        )

                        if current is None:
                            new_state = (
                                observation.mapped_state or WorkflowState.REQUESTED
                            )
                            processing_state = ProcessingState.IN_SYNC
                            logger.info(
                                "new request %s from %s/%s -> %s",
                                observation.external_request_id,
                                provider.display_name,
                                feed,
                                new_state.value,
                            )
                            logger.info(
                                "===> new_state: %s, processing_state: %s",
                                new_state,
                                processing_state,
                            )
                            logger.info(
                                "EFFECTS ===> (observation, from_state, new_state): (%s,%s,%s)",
                                observation.direction,
                                from_state,
                                new_state,
                            )

                            # queued_effects = plan_effects(
                            #     observation,
                            #     from_workflow_state=from_state,
                            #     to_workflow_state=new_state,
                            #     processing_state=processing_state,
                            #     provider=adapter,
                            # )
                            # logger.info(
                            #     "===> queued_effects: %s",
                            #     queued_effects,
                            # )
                        elif from_state == observation.mapped_state:
                            new_state = from_state or WorkflowState.REQUESTED
                            processing_state = ProcessingState.IN_SYNC
                        else:
                            try:
                                if (
                                    from_state is None
                                    or observation.mapped_state is None
                                ):
                                    raise InvalidWorkflowTransition(
                                        "missing current or observed workflow state"
                                    )
                                logger.info(
                                    "===> Transitioning from %s to %s",
                                    from_state,
                                    observation.mapped_state,
                                )
                                new_state = (
                                    Workflow(from_state)
                                    .transition_to(observation.mapped_state)
                                    .state
                                )
                                processing_state = ProcessingState.IN_SYNC
                                logger.info(
                                    "state transition %s: %s -> %s",
                                    observation.external_request_id,
                                    from_state.value,
                                    new_state.value,
                                )
                            except InvalidWorkflowTransition as exc:
                                new_state = from_state or WorkflowState.REQUESTED
                                processing_state = ProcessingState.CONFLICT
                                logger.warning(
                                    "refused transition for %s: %s",
                                    observation.external_request_id,
                                    exc,
                                )

                        if observation.needs_review:
                            processing_state = ProcessingState.NEEDS_REVIEW
                            logger.warning(
                                "request %s needs review: status=%r code=%r",
                                observation.external_request_id,
                                observation.provider_status_raw,
                                observation.provider_status_code,
                            )

                        logger.info(
                            "===>SYNC Applying effects for observation %s from %s to %s with processing state %s",
                            observation.external_request_id,
                            from_state,
                            new_state,
                            processing_state,
                        )
                        _, queued_effects = await repository.apply_observation(
                            tenant_id=provider.tenant_id,
                            obs=observation,
                            provider=provider,
                            adapter=adapter,
                            request_id=current.id if current else uuid.uuid4(),
                            from_state=from_state,
                            new_state=new_state,
                            processing_state=processing_state,
                            expected_version=current.version if current else None,
                            current_processing_state=(
                                current.processing_state if current else None
                            ),
                        )
                        if queued_effects:
                            logger.info(
                                "queued effects for %s: %s",
                                observation.external_request_id,
                                ", ".join(effect.value for effect in queued_effects),
                            )

                    if new_events:
                        logger.info(
                            "%s/%s processed %d new event(s) from %d record(s)",
                            provider.display_name,
                            feed,
                            new_events,
                            page.count,
                        )

            await session.commit()
    finally:
        await engine.dispose()


async def main() -> None:
    configure_logging()
    while True:
        try:
            await poll_enabled_providers()
        except Exception:
            logger.exception("provider polling cycle failed")
        await wait_for_next_poll()


if __name__ == "__main__":
    asyncio.run(main())
    # asyncio.run(
    #     apply_effects([EffectKind.FOLIO_ADD_REQUESTING_LIBRARY])
    # )
