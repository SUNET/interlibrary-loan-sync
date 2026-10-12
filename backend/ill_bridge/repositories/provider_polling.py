from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from ill_bridge.common.effects import EffectKind, plan_effects
from ill_bridge.common.exceptions import ProviderNotFound, StaleVersionError
from ill_bridge.common.models import ProviderRequestObservation
from ill_bridge.common.states import ProcessingState, WorkflowState
from ill_bridge.database.models import (
    EffectQueue,
    IllRequests,
    Providers,
    RawProviderRequests,
    RequestParties,
    StateAuditLogs,
    Tenants,
)
from ill_bridge.providers.base import IllProvider
from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ProviderRef:
    """Credential-free provider data used by cross-tenant schedulers."""

    id: UUID
    tenant_id: UUID
    adapter_key: str
    local_library_code: str
    poll_interval_seconds: int


class ProviderPollingRepository:
    """Coordinates provider polling persistence across provider and ILL tables."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_enabled_providers(self) -> list[ProviderRef]:
        """List credential-free enabled providers for cross-tenant scheduling."""
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

    async def get_tenant(self, tenant_id: UUID) -> Tenants | None:
        """Return a tenant by id, or None when it does not exist."""
        return await self._session.get(Tenants, tenant_id)

    async def get_provider_by_id_for_tenant(
        self, tenant_id: UUID, provider_id: UUID
    ) -> Providers | None:
        """Return a provider only when it belongs to the supplied tenant."""
        result = await self._session.execute(
            select(Providers).where(
                Providers.id == provider_id,
                Providers.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_required_provider_for_tenant(
        self, tenant_id: UUID, provider_id: UUID
    ) -> Providers:
        """Return a tenant provider or raise when it is absent."""
        provider = await self.get_provider_by_id_for_tenant(tenant_id, provider_id)
        if provider is None:
            raise ProviderNotFound(
                f"Provider {provider_id} not found for tenant {tenant_id}"
            )
        return provider

    async def _sync_parties_for_observation(
        self,
        *,
        tenant_id: UUID,
        ill_request_id: UUID,
        observation: ProviderRequestObservation,
    ) -> list[RequestParties]:
        """Replace the provider's ordered party list for one ILL request."""
        await self._session.execute(
            delete(RequestParties).where(
                RequestParties.tenant_id == tenant_id,
                RequestParties.ill_request_id == ill_request_id,
            )
        )
        request_parties = []
        for ordinal, recipient in enumerate(observation.recipients):
            is_active = bool(recipient.is_active_library)
            role = "ACTIVE_LENDER" if is_active else "LENDER_CANDIDATE"
            request_parties.append(
                RequestParties(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    ill_request_id=ill_request_id,
                    role=role,
                    scheme="SIGEL",
                    code=recipient.library_code,
                    ordinal=ordinal,
                    is_active=is_active,
                    response_code=recipient.response_id,
                    response_at=recipient.response_date,
                    location=recipient.location or None,
                )
            )
        self._session.add_all(request_parties)
        await self._session.flush()
        return request_parties

    async def apply_observation(
        self,
        *,
        tenant_id: UUID,
        obs: ProviderRequestObservation,
        provider: Providers,
        adapter: IllProvider,
        request_id: UUID,
        from_state: WorkflowState | None,
        new_state: WorkflowState,
        processing_state: ProcessingState,
        expected_version: int | None,
        current_processing_state: str | None = None,
    ) -> tuple[int, tuple[EffectKind, ...]]:
        """Apply an observation to the canonical ILL request.

        Observations that change neither the workflow state nor the processing
        state are treated as no-ops: no version bump, audit log or effects.
        """
        from_workflow_state = from_state.value if from_state is not None else None
        to_workflow_state = new_state.value
        processing_state_value = processing_state.value

        if (
            expected_version is not None
            and from_state == new_state
            and current_processing_state == processing_state_value
        ):
            # No-op observation: neither workflow nor processing state changed.
            # Refresh provider-side fields and parties, but do not bump the
            # version, write an audit row, or queue effects.
            await self.touch_ill_request_from_observation(
                tenant_id=tenant_id,
                ill_request_id=request_id,
                observation=obs,
            )
            await self._sync_parties_for_observation(
                tenant_id=tenant_id,
                ill_request_id=request_id,
                observation=obs,
            )
            return expected_version, ()

        if expected_version is None:
            # Create a new ILL request from the observation
            ill_request = await self.create_ill_request_from_observation(
                ill_request_id=request_id,
                tenant_id=tenant_id,
                provider_id=provider.id,
                observation=obs,
                workflow_state=to_workflow_state,
                processing_state=processing_state_value,
                mapping_version=provider.mapping_version,
            )
            request_version = ill_request.version
        else:
            # Update the existing ILL request with the observation
            updated = await self.update_ill_request_from_observation(
                tenant_id=tenant_id,
                ill_request_id=request_id,
                expected_version=expected_version,
                observation=obs,
                workflow_state=to_workflow_state,
                processing_state=processing_state_value,
            )
            if not updated:
                # result.rowcount != 1, does exist or match expected version , so raise StaleVersionError
                raise StaleVersionError(
                    f"Failed to update ILL request {request_id} for tenant {tenant_id}: stale version"
                )
            request_version = expected_version + 1

        # 1. sync parties
        await self._sync_parties_for_observation(
            tenant_id=tenant_id,
            ill_request_id=request_id,
            observation=obs,
        )
        # 2. update StateAuditLog
        await self.add_ill_request_observation_audit_log(
            tenant_id=tenant_id,
            ill_request_id=request_id,
            observation=obs,
            from_workflow_state=from_workflow_state,
            to_workflow_state=to_workflow_state,
            mapping_version=provider.mapping_version,
            request_version=request_version,
        )
        # 3. queue effects for downstream processing
        queued_effects = plan_effects(
            obs,
            from_workflow_state=from_state,
            to_workflow_state=new_state,
            processing_state=processing_state,
            provider=adapter,
        )
        for effect_kind in queued_effects:
            await self.add_ill_request_effect_queue_entry(
                tenant_id=tenant_id,
                ill_request_id=request_id,
                effect_kind=effect_kind,
                from_workflow_state=from_state,
                to_workflow_state=new_state,
                context={
                    "receiving_library": (
                        obs.receiving_library.model_dump()
                        if obs.receiving_library
                        else None
                    ),
                },
            )
        return request_version, queued_effects

    async def create_ill_request_from_observation(
        self,
        *,
        ill_request_id: UUID,
        tenant_id: UUID,
        provider_id: UUID,
        observation: ProviderRequestObservation,
        workflow_state: str,
        processing_state: str,
        mapping_version: str,
    ) -> IllRequests:
        """Create the canonical ILL request represented by an observation."""
        ill_request = IllRequests(
            id=ill_request_id,
            tenant_id=tenant_id,
            provider_id=provider_id,
            external_request_id=observation.external_request_id,
            provider_record_id=observation.provider_record_id,
            direction=observation.direction,
            request_type=observation.request_type,
            workflow_state=workflow_state,
            processing_state=processing_state,
            requesting_library=observation.requesting_library.model_dump(),
            active_lending_library=(
                observation.active_lending_library.model_dump()
                if observation.active_lending_library
                else None
            ),
            bibliographic=observation.bibliographic.model_dump(),
            provider_status_raw=observation.provider_status_raw,
            provider_status_code=observation.provider_status_code,
            provider_revision=observation.provider_revision,
            extensions=observation.extensions,
            observed_at=observation.observed_at,
            mapping_version=mapping_version,
            version=1,
        )
        self._session.add(ill_request)
        await self._session.flush()
        return ill_request

    async def update_ill_request_from_observation(
        self,
        *,
        tenant_id: UUID,
        ill_request_id: UUID,
        expected_version: int,
        observation: ProviderRequestObservation,
        workflow_state: str,
        processing_state: str,
    ) -> bool:
        """Apply an observation only if the canonical request version is current."""
        statement = (
            update(IllRequests)
            .where(
                IllRequests.tenant_id == tenant_id,
                IllRequests.id == ill_request_id,
                IllRequests.version == expected_version,
            )
            .values(
                workflow_state=workflow_state,
                processing_state=processing_state,
                provider_status_raw=observation.provider_status_raw,
                provider_status_code=observation.provider_status_code,
                provider_revision=observation.provider_revision,
                observed_at=observation.observed_at,
                version=expected_version + 1,
                updated_at=func.now(),
            )
        )
        # SQLAlchemy types AsyncSession.execute broadly; UPDATE returns a cursor result.
        # So we know if another process has updated the row if the rowcount is not 1,
        # and we can raise a StaleVersionError.
        result = cast(
            CursorResult[Any],
            await self._session.execute(statement),
        )
        return result.rowcount == 1

    async def touch_ill_request_from_observation(
        self,
        *,
        tenant_id: UUID,
        ill_request_id: UUID,
        observation: ProviderRequestObservation,
    ) -> None:
        """Refresh provider-side fields without changing state or version."""
        await self._session.execute(
            update(IllRequests)
            .where(
                IllRequests.tenant_id == tenant_id,
                IllRequests.id == ill_request_id,
            )
            .values(
                provider_status_raw=observation.provider_status_raw,
                provider_status_code=observation.provider_status_code,
                provider_revision=observation.provider_revision,
                observed_at=observation.observed_at,
            )
        )

    async def add_ill_request_observation_audit_log(
        self,
        *,
        tenant_id: UUID,
        ill_request_id: UUID,
        observation: ProviderRequestObservation,
        from_workflow_state: str | None,
        to_workflow_state: str,
        mapping_version: str,
        request_version: int,
        event_type: str = "OBSERVATION",
        actor_type: str = "PROVIDER",
    ) -> StateAuditLogs:
        """Record the provider observation that produced an ILL request state."""
        audit_log = StateAuditLogs(
            id=uuid4(),
            tenant_id=tenant_id,
            ill_request_id=ill_request_id,
            event_type=event_type,
            from_state=from_workflow_state,
            to_state=to_workflow_state,
            actor_type=actor_type,
            source_event_key=observation.event_key,
            correlation_id=observation.correlation_id,
            mapping_version=mapping_version,
            request_version=request_version,
            occurred_at=observation.observed_at,
        )
        self._session.add(audit_log)
        await self._session.flush()
        return audit_log

    async def add_ill_request_effect_queue_entry(
        self,
        *,
        tenant_id: UUID,
        ill_request_id: UUID,
        effect_kind: str,
        from_workflow_state: WorkflowState | None,
        to_workflow_state: WorkflowState,
        context: dict[str, Any] | None = None,
    ) -> EffectQueue:
        """Queue one downstream effect for an ILL request state transition.

        `context` is a snapshot of the observation data the effect handler
        needs, so the dispatcher does not have to re-derive it later.
        """
        effect_queue_entry = EffectQueue(
            id=uuid4(),
            tenant_id=tenant_id,
            ill_request_id=ill_request_id,
            kind=effect_kind,
            effect_key=f"{ill_request_id}:{to_workflow_state.value}:{effect_kind}",
            payload={
                "from": (
                    from_workflow_state.value
                    if from_workflow_state is not None
                    else None
                ),
                "to": to_workflow_state.value,
                **(context or {}),
            },
        )
        self._session.add(effect_queue_entry)
        await self._session.flush()
        return effect_queue_entry

    async def replace_ill_request_parties(
        self,
        *,
        tenant_id: UUID,
        ill_request_id: UUID,
        parties: list[dict[str, Any]],
    ) -> list[RequestParties]:
        """Replace the provider's ordered party list for one ILL request."""
        await self._session.execute(
            delete(RequestParties).where(
                RequestParties.tenant_id == tenant_id,
                RequestParties.ill_request_id == ill_request_id,
            )
        )
        request_parties = [
            RequestParties(
                id=uuid4(),
                tenant_id=tenant_id,
                ill_request_id=ill_request_id,
                role=party.get("role", "LENDER_CANDIDATE"),
                scheme=party.get("scheme", "SIGEL"),
                code=party["library_code"],
                ordinal=ordinal,
                is_active=bool(party.get("is_active_library")),
                response_code=party.get("response_id"),
                response_at=party.get("response_date"),
                location=party.get("location") or None,
            )
            for ordinal, party in enumerate(parties)
        ]
        self._session.add_all(request_parties)
        await self._session.flush()
        return request_parties

    async def get_ill_request_by_id_for_tenant(
        self, tenant_id: UUID, ill_request_id: UUID
    ) -> IllRequests | None:
        """Return one request only when it belongs to the supplied tenant."""
        result = await self._session.execute(
            select(IllRequests).where(
                IllRequests.tenant_id == tenant_id,
                IllRequests.id == ill_request_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_ill_request_by_provider_external_identity(
        self,
        tenant_id: UUID,
        provider_id: UUID,
        observation: ProviderRequestObservation,
    ) -> IllRequests | None:
        """Find the canonical request represented by a provider observation."""
        result = await self._session.execute(
            select(IllRequests).where(
                IllRequests.tenant_id == tenant_id,
                IllRequests.provider_id == provider_id,
                IllRequests.direction == observation.direction,
                IllRequests.external_request_id == observation.external_request_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_ill_requests_for_tenant(
        self, tenant_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[IllRequests]:
        """List a tenant's requests, most recently updated first."""
        result = await self._session.execute(
            select(IllRequests)
            .where(IllRequests.tenant_id == tenant_id)
            .order_by(IllRequests.updated_at.desc(), IllRequests.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def record_raw_provider_event(
        self,
        *,
        tenant_id: UUID,
        provider_id: UUID,
        source_key: str,
        event_key: str,
        payload: dict[str, Any],
    ) -> bool:
        """Store an upstream event once; return False when it was already seen."""
        payload_hash = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        statement = (
            insert(RawProviderRequests)
            .values(
                id=uuid4(),
                tenant_id=tenant_id,
                provider_id=provider_id,
                source_key=source_key,
                event_key=event_key,
                payload=payload,
                payload_hash=payload_hash,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "source_key", "event_key"]
            )
            .returning(RawProviderRequests.id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def mark_raw_provider_event_processed(
        self, tenant_id: UUID, raw_provider_event_id: UUID, *, processing_result: str
    ) -> RawProviderRequests | None:
        """Mark a raw event as processed and retain its processing outcome."""
        raw_event = await self._session.scalar(
            select(RawProviderRequests).where(
                RawProviderRequests.tenant_id == tenant_id,
                RawProviderRequests.id == raw_provider_event_id,
            )
        )
        if raw_event is None:
            return None

        raw_event.processed_at = datetime.now(timezone.utc)
        raw_event.result = processing_result
        await self._session.flush()
        return raw_event
