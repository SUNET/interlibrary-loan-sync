"""Create-order tests (A5) against a real PostgreSQL container.

Two angles on the same write:

* **Service + repository** -- ``BorrowingOrderService.create_order`` run
  directly against a session, asserting the order row *and* its queued
  infodisk effect are persisted together.
* **API** -- the same flow through ``POST /api/v1/borrowing/orders``,
  asserting the HTTP contract and then re-reading the database to prove the
  endpoint committed.

FOLIO is faked in both (see ``folio_client_factory`` in conftest): the patron
check must never reach the network. The schema and a seeded tenant come from
the ``borrowing_env`` fixture.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ill_bridge.api.main import create_app
from ill_bridge.common.effects import EffectKind
from ill_bridge.common.enums import RequestType
from ill_bridge.common.states import BorrowingOrderState, FolioUserStatus
from ill_bridge.database.models import BorrowingOrders, EffectQueue
from ill_bridge.database.session import make_engine, make_sessionmaker
from ill_bridge.repositories.borrowing_orders import BorrowingOrderRepository
from ill_bridge.services.borrowing_orders import BorrowingOrderService


async def _scope_tenant(session: AsyncSession, tenant_id) -> None:
    """Set the transaction-local tenant id the repository scopes queries to."""
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )


def test_create_order_persists_order_and_effect(
    borrowing_env, folio_client_factory
) -> None:
    folio_user_id = uuid4()
    order_id = uuid4()

    async def _run() -> None:
        engine = create_async_engine(borrowing_env.async_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessionmaker() as session:
                await _scope_tenant(session, borrowing_env.tenant_id)
                service = BorrowingOrderService(
                    BorrowingOrderRepository(session),
                    folio_client=folio_client_factory(
                        users=[{"id": str(folio_user_id)}]
                    ),
                )
                order, created = await service.create_order(
                    tenant_id=borrowing_env.tenant_id,
                    request_type=RequestType.LOAN,
                    bibliographic={"title": "Deep Work"},
                    patron_barcode="900123",
                    patron_name="Ada Lovelace",
                    order_id=order_id,
                )
                assert created is True
                assert order.id == order_id
                assert order.folio_user_status == FolioUserStatus.FOUND.value
                assert order.folio_user_id == folio_user_id
                await session.commit()

            # Re-read in a fresh session: order and effect are durable and
            # committed together.
            async with sessionmaker() as session:
                await _scope_tenant(session, borrowing_env.tenant_id)
                row = (
                    await session.execute(
                        select(BorrowingOrders).where(BorrowingOrders.id == order_id)
                    )
                ).scalar_one()
                assert row.state == BorrowingOrderState.SUBMITTED.value
                assert row.processing_state == "UNHANDLED"
                assert row.patron_name == "Ada Lovelace"
                assert row.bibliographic == {"title": "Deep Work"}

                effects = (
                    await session.execute(
                        select(EffectQueue).where(
                            EffectQueue.borrowing_order_id == order_id
                        )
                    )
                ).scalars().all()
                assert [e.kind for e in effects] == [EffectKind.NOTIFY_INFODISK.value]
                assert effects[0].effect_key == (
                    f"{order_id}:SUBMITTED:NOTIFY_INFODISK"
                )
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_create_order_is_idempotent_on_repeated_id(
    borrowing_env, folio_client_factory
) -> None:
    order_id = uuid4()

    async def _run() -> None:
        engine = create_async_engine(borrowing_env.async_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

        async def _create() -> bool:
            async with sessionmaker() as session:
                await _scope_tenant(session, borrowing_env.tenant_id)
                service = BorrowingOrderService(
                    BorrowingOrderRepository(session),
                    folio_client=folio_client_factory(users=[]),
                )
                _, created = await service.create_order(
                    tenant_id=borrowing_env.tenant_id,
                    request_type=RequestType.COPY,
                    bibliographic={"title": "Once"},
                    patron_barcode="900999",
                    patron_name="Grace Hopper",
                    order_id=order_id,
                )
                await session.commit()
                return created

        try:
            assert await _create() is True
            # Same id again: the stored order is returned, nothing new written.
            assert await _create() is False

            async with sessionmaker() as session:
                await _scope_tenant(session, borrowing_env.tenant_id)
                effects = (
                    await session.execute(
                        select(EffectQueue).where(
                            EffectQueue.borrowing_order_id == order_id
                        )
                    )
                ).scalars().all()
                # A retried create must not queue a second infodisk mail.
                assert len(effects) == 1
        finally:
            await engine.dispose()

    asyncio.run(_run())


def test_create_order_via_api_persists_to_database(
    borrowing_env, folio_client_factory, monkeypatch
) -> None:
    folio_user_id = uuid4()
    order_id = uuid4()
    settings = borrowing_env.settings

    @asynccontextmanager
    async def test_lifespan(app):
        # Wire the engine inside the TestClient event loop, bypassing the real
        # lifespan (and its Procrastinate pool, irrelevant to order intake).
        engine = make_engine(settings)
        app.state.engine = engine
        app.state.sessionmaker = make_sessionmaker(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = create_app()
    app.router.lifespan_context = test_lifespan
    # Intake must never reach the real FOLIO: hand the router a fake client.
    monkeypatch.setattr(
        "ill_bridge.api.v1.borrowing.router.get_folio_client",
        lambda tenant_key: folio_client_factory(users=[{"id": str(folio_user_id)}]),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/borrowing/orders",
            headers={"X-Tenant-Id": str(borrowing_env.tenant_id)},
            json={
                "order_id": str(order_id),
                "request_type": "LOAN",
                "bibliographic": {"title": "Deep Work"},
                "patron_barcode": "900123",
                "patron_name": "Ada Lovelace",
            },
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == str(order_id)
    assert body["state"] == "SUBMITTED"
    assert body["folio_user_status"] == "FOUND"
    assert body["folio_user_id"] == str(folio_user_id)

    async def _read() -> tuple[str, list[str]]:
        engine = create_async_engine(borrowing_env.async_url)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessionmaker() as session:
                await _scope_tenant(session, borrowing_env.tenant_id)
                row = (
                    await session.execute(
                        select(BorrowingOrders).where(BorrowingOrders.id == order_id)
                    )
                ).scalar_one()
                effects = (
                    await session.execute(
                        select(EffectQueue).where(
                            EffectQueue.borrowing_order_id == order_id
                        )
                    )
                ).scalars().all()
                return row.patron_name, [e.kind for e in effects]
        finally:
            await engine.dispose()

    patron_name, effect_kinds = asyncio.run(_read())
    assert patron_name == "Ada Lovelace"
    assert effect_kinds == [EffectKind.NOTIFY_INFODISK.value]
