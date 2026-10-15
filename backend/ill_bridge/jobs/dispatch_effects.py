"""Execute queued ``effect_queue`` rows (first draft).

See docs/step3/side-effect-EffectQueueEntry.md for the full design. This draft
keeps the essential safety properties and leaves the rest as TODOs:

Kept:
  * Leased claiming with ``FOR UPDATE SKIP LOCKED`` (no row handled twice).
  * ``fence`` checked on every completion write (zombie workers are ignored).
  * Four explicit outcomes: CONFIRMED / REFUSED / TRANSIENT / UNKNOWN.
  * UNKNOWN is never blindly retried immediately.
  * Nothing is silently dropped: unhandled kinds stay queued and flag the
    request as NEEDS_REVIEW.

Not yet (TODO):
  * ``sync_operations`` ledger and reconciliation of UNKNOWN outcomes.
  * A real DLQ table; exhausted retries are published with ``last_error``.
  * Handlers other than FOLIO_ADD_REQUESTING_LIBRARY.

Run with:  python -m ill_bridge.jobs.dispatch_effects
secretspec run -- uv run python -m ill_bridge.jobs.dispatch_effects
dotenvx run -f /home/benedith/github/library_project/interlibrary_loan_system/mvp/python/ill-bridge/deploy/.env -- uv run python -m ill_bridge.jobs.dispatch_effects
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID

import httpx2
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.common.effects import EffectKind
from ill_bridge.common.folio_client import (
    FolioApiClient,
    create_folio_requesting_library,
    get_folio_client,
)
from ill_bridge.common.models import ReceivingLibrary
from ill_bridge.common.states import ProcessingState
from ill_bridge.config import FOLIO_TENANT_PATRON_GROUPS, Settings
from ill_bridge.database.models import EffectQueue, IllRequests, Tenants
from ill_bridge.database.session import make_engine, make_sessionmaker

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 10.0
BATCH_SIZE = 20
LEASE_SECONDS = 60
MAX_ATTEMPTS = 6
UNKNOWN_RECHECK = timedelta(minutes=5)
UNHANDLED_RECHECK = timedelta(hours=1)
WORKER = f"{socket.gethostname()}:{os.getpid()}"


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


class Outcome(StrEnum):
    CONFIRMED = "CONFIRMED"  # it definitely happened
    REFUSED = "REFUSED"  # the target said no, permanently
    TRANSIENT = "TRANSIENT"  # retry is safe and expected
    UNKNOWN = "UNKNOWN"  # we do not know whether it happened


@dataclass(frozen=True)
class EffectOutcome:
    outcome: Outcome
    external_id: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class EffectContext:
    """Everything a handler needs. Handlers get no DB session on purpose:
    only the dispatcher writes to our database."""

    tenant: Tenants
    ill_request: IllRequests
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

Handler = Callable[[EffectContext], Awaitable[EffectOutcome]]
_HANDLERS: dict[EffectKind, Handler] = {}


def handles(kind: EffectKind) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        if kind in _HANDLERS:
            raise RuntimeError(f"duplicate handler for {kind}")
        _HANDLERS[kind] = fn
        return fn

    return register


def handler_for(kind: str) -> Handler | None:
    try:
        return _HANDLERS.get(EffectKind(kind))
    except ValueError:
        return None


def _outcome_from_http_error(exc: Exception, *, idempotent: bool) -> EffectOutcome:
    """Translate an HTTP failure into an outcome.

    A timeout/transport error means we do not know if the call landed. If the
    handler is idempotent (it checks before it writes), retrying is safe, so
    it is TRANSIENT; otherwise it is UNKNOWN.
    """
    if isinstance(exc, httpx2.HTTPStatusError):
        status = exc.response.status_code
        if status >= 500 or status == 429:
            return EffectOutcome(Outcome.TRANSIENT, detail=f"HTTP {status}")
        return EffectOutcome(
            Outcome.REFUSED, detail=f"HTTP {status}: {exc.response.text[:200]}"
        )
    if isinstance(exc, httpx2.RequestError):
        kind = Outcome.TRANSIENT if idempotent else Outcome.UNKNOWN
        return EffectOutcome(kind, detail=f"{type(exc).__name__}: {exc}")
    raise exc


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

_folio_clients: dict[str, FolioApiClient] = {}


def _folio(tenant_key: str | None = None) -> FolioApiClient:
    # Lazy so importing this module does not require FOLIO env vars.
    key = (tenant_key or os.getenv("ILL_TENANT_NAME", "bth")).lower()
    if key not in _folio_clients:
        _folio_clients[key] = get_folio_client(key)
    return _folio_clients[key]


@handles(EffectKind.FOLIO_ADD_REQUESTING_LIBRARY)
async def add_requesting_library(ctx: EffectContext) -> EffectOutcome:
    """Create the requesting library as a FOLIO user.

    Idempotent: create_folio_requesting_library looks the user up by
    username first, so a retry after a timeout cannot create a duplicate.
    """
    data = ctx.payload.get("receiving_library")
    if not data:
        return EffectOutcome(Outcome.REFUSED, detail="no receiving_library in payload")

    patron_group = FOLIO_TENANT_PATRON_GROUPS.get(ctx.tenant.folio_tenant_key)
    if patron_group is None or not patron_group.uuid:
        return EffectOutcome(
            Outcome.REFUSED,
            detail=f"no patron group configured for {ctx.tenant.folio_tenant_key}",
        )

    try:
        logger.info(
            "creating FOLIO requesting library for tenant %s: %s",
            ctx.tenant.id,
            data,
        )
        result = await create_folio_requesting_library(
            client=_folio(ctx.tenant.folio_tenant_key),
            receiving_library=ReceivingLibrary(**data),
            patron_group_id=patron_group.uuid,
        )
    except (httpx2.HTTPStatusError, httpx2.RequestError) as exc:
        return _outcome_from_http_error(exc, idempotent=True)

    return EffectOutcome(Outcome.CONFIRMED, external_id=result.get("id"))


# TODO: FOLIO_OPEN_LOAN, FOLIO_RENEW_LOAN, FOLIO_CLOSE_LOAN,
#       FOLIO_PROVISION_ITEM, NOTIFY_PATRON_PICKUP, PROVIDER_* handlers.


# ---------------------------------------------------------------------------
# Persistence (only the dispatcher writes)
# ---------------------------------------------------------------------------

CLAIM_SQL = text(
    """
    WITH claimable AS (
        SELECT id
        FROM effect_queue
        WHERE tenant_id = :tenant_id
          AND published_at IS NULL
          AND available_at <= now()
          AND (claimed_until IS NULL OR claimed_until < now())
        ORDER BY available_at
        FOR UPDATE SKIP LOCKED
        LIMIT :batch
    )
    UPDATE effect_queue q
       SET claimed_by    = :worker,
           claimed_until = now() + make_interval(secs => :lease_seconds),
           fence         = q.fence + 1
      FROM claimable c
     WHERE q.id = c.id
    RETURNING q.id, q.tenant_id, q.ill_request_id, q.kind, q.payload,
              q.effect_key, q.attempts, q.fence
    """
)


async def _set_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Scope row-level security to one tenant for this transaction."""
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


async def _claim(session: AsyncSession, tenant_id: UUID) -> list[dict[str, Any]]:
    result = await session.execute(
        CLAIM_SQL,
        {
            "tenant_id": tenant_id,
            "worker": WORKER,
            "batch": BATCH_SIZE,
            "lease_seconds": LEASE_SECONDS,
        },
    )
    rows = [dict(row) for row in result.mappings().all()]
    logger.debug("claimed %d effect(s) for tenant %s", len(rows), tenant_id)
    return rows


async def _finish(
    session: AsyncSession,
    row: dict[str, Any],
    *,
    published: bool,
    attempts: int | None = None,
    available_at: datetime | None = None,
    last_error: str | None = None,
) -> bool:
    """Complete or release a claimed row. Rejected if our fence is stale."""
    values: dict[str, Any] = {
        "claimed_by": None,
        "claimed_until": None,
        "last_error": last_error,
    }
    if published:
        values["published_at"] = _utcnow()
    if attempts is not None:
        values["attempts"] = attempts
    if available_at is not None:
        values["available_at"] = available_at

    result = await session.execute(
        update(EffectQueue)
        .where(EffectQueue.id == row["id"], EffectQueue.fence == row["fence"])
        .values(**values)
    )
    if result.rowcount != 1:
        logger.warning("stale fence for effect %s; another worker owns it", row["id"])
        return False
    return True


async def _set_processing_state(
    session: AsyncSession, row: dict[str, Any], state: ProcessingState
) -> None:
    if row["ill_request_id"] is None:
        return
    await session.execute(
        update(IllRequests)
        .where(
            IllRequests.tenant_id == row["tenant_id"],
            IllRequests.id == row["ill_request_id"],
        )
        .values(processing_state=state.value)
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _backoff(attempt: int) -> datetime:
    """Exponential with jitter: ~10s, 20s, 40s ... capped at 10 minutes."""
    base = min(10 * 2 ** (attempt - 1), 600)
    return _utcnow() + timedelta(seconds=base * (0.5 + random.random()))


async def _execute_one(
    session: AsyncSession, tenant: Tenants, row: dict[str, Any]
) -> None:
    kind = row["kind"]
    handler = handler_for(kind)
    print(f"Executing effect {row['id']} of kind {kind} for tenant {tenant.id}")  # Debugging line
    print("Handler:", handler)  # Debugging line
    if handler is None:
        # Never drop an obligation: keep it queued and ask a human.
        logger.warning("no handler for effect %s (%s)", kind, row["id"])
        if await _finish(
            session,
            row,
            published=False,
            available_at=_utcnow() + UNHANDLED_RECHECK,
            last_error=f"no handler for {kind}",
        ):
            await _set_processing_state(session, row, ProcessingState.NEEDS_REVIEW)
        return

    ill_request = await session.get(IllRequests, row["ill_request_id"])
    if ill_request is None:
        await _finish(
            session, row, published=True, last_error="ill_request not found"
        )
        return

    ctx = EffectContext(tenant=tenant, ill_request=ill_request, payload=row["payload"])
    try:
        result = await handler(ctx)
    except Exception as exc:  # a handler bug must not kill the whole batch
        logger.exception("handler %s crashed for effect %s", kind, row["id"])
        result = EffectOutcome(Outcome.UNKNOWN, detail=f"handler crashed: {exc}")

    await _record(session, row, result)


async def _record(
    session: AsyncSession, row: dict[str, Any], result: EffectOutcome
) -> None:
    attempts = row["attempts"] + 1
    logger.info(
        "effect %s %s -> %s %s",
        row["kind"],
        row["id"],
        result.outcome,
        result.detail or "",
    )

    if result.outcome is Outcome.CONFIRMED:
        if await _finish(session, row, published=True, attempts=attempts):
            await _set_processing_state(session, row, ProcessingState.IN_SYNC)

    elif result.outcome is Outcome.REFUSED:
        # Finished, as a "no". Do not retry a decision the target already made.
        if await _finish(
            session, row, published=True, attempts=attempts, last_error=result.detail
        ):
            await _set_processing_state(session, row, ProcessingState.CONFLICT)

    elif result.outcome is Outcome.TRANSIENT:
        if attempts >= MAX_ATTEMPTS:
            # TODO: move to a DLQ table instead of publishing.
            if await _finish(
                session,
                row,
                published=True,
                attempts=attempts,
                last_error=f"abandoned after {attempts} attempts: {result.detail}",
            ):
                await _set_processing_state(session, row, ProcessingState.NEEDS_REVIEW)
        elif await _finish(
            session,
            row,
            published=False,
            attempts=attempts,
            available_at=_backoff(attempts),
            last_error=result.detail,
        ):
            await _set_processing_state(session, row, ProcessingState.RETRYING)

    else:  # UNKNOWN
        # TODO: reconcile via sync_operations instead of re-running blindly.
        if await _finish(
            session,
            row,
            published=False,
            attempts=attempts,
            available_at=_utcnow() + UNKNOWN_RECHECK,
            last_error=result.detail,
        ):
            await _set_processing_state(session, row, ProcessingState.CONFLICT)


async def dispatch_effects(sessionmaker) -> int:
    """Run one dispatch pass over all tenants. Returns effects handled."""
    handled = 0
    async with sessionmaker() as session:
        tenants = (await session.execute(select(Tenants))).scalars().all()
        
    print(f"Dispatching effects for tenants: {[tenant.id for tenant in tenants]}")  # Debugging line
    for tenant in tenants:
        # One transaction per tenant: a failure in one tenant does not roll
        # back another tenant's completed effects.
        async with sessionmaker() as session:
            async with session.begin():
                await _set_tenant(session, tenant.id)
                rows = await _claim(session, tenant.id)
            # Lease is committed; now execute, committing per effect so a
            # crash mid-batch keeps earlier results.
            for row in rows:
                print(f"Dispatching effect {row['id']} for tenant {tenant.id}")  # Debugging line
                async with session.begin():
                    await _set_tenant(session, tenant.id)
                    await _execute_one(session, tenant, row)
                handled += 1
    return handled


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)
    try:
        while True:
            try:
                count = await dispatch_effects(sessionmaker)
                if count:
                    logger.info("dispatched %d effect(s)", count)
            except Exception:
                logger.exception("effect dispatch cycle failed")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        try:
            await asyncio.gather(*(client.close() for client in _folio_clients.values()))
        finally:
            _folio_clients.clear()
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
