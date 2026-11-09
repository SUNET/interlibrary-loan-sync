from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from ill_bridge.common.enums import IllSubjectType
from ill_bridge.common.exceptions import BorrowingOrderNotFound
from ill_bridge.common.states import (
    BorrowingOrderProcessingState,
    BorrowingOrderState,
)
from ill_bridge.database.models import BorrowingOrders, EffectQueue
from sqlalchemy import delete as sql_delete, func, select, update as sql_update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction


class BorrowingOrderRepository:
    """Database access for ``borrowing_orders`` and the effects they own.

    Persistence only: no business rules, no effect planning. Composition of
    these calls belongs in :class:`~ill_bridge.services.borrowing_orders.
    BorrowingOrderService`.

    The caller owns the transaction and must have set ``app.tenant_id``;
    row-level security filters every statement here. Every method also takes
    ``tenant_id`` explicitly, so a missing RLS setting shows up as a missing
    row rather than as another tenant's data.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def savepoint(self) -> AsyncSessionTransaction:
        """Open a SAVEPOINT around a write that may violate a constraint.

        A failed statement poisons the whole transaction in PostgreSQL, so a
        caller that wants to turn a constraint violation into a typed error
        has to isolate the write. Without this, one rejected duplicate
        reference would also discard the order insert that preceded it in the
        same request.
        """
        return self._session.begin_nested()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(self, *, tenant_id: UUID, order_id: UUID) -> BorrowingOrders | None:
        """Return one order, or None when it does not exist for this tenant."""
        result = await self._session.execute(
            select(BorrowingOrders).where(
                BorrowingOrders.tenant_id == tenant_id,
                BorrowingOrders.id == order_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_required(
        self, *, tenant_id: UUID, order_id: UUID
    ) -> BorrowingOrders:
        """Return one order, raising when it is absent."""
        order = await self.get(tenant_id=tenant_id, order_id=order_id)
        if order is None:
            raise BorrowingOrderNotFound(
                f"Borrowing order {order_id} not found for tenant {tenant_id}"
            )
        return order

    async def get_by_tenant(
        self,
        *,
        tenant_id: UUID,
        state: BorrowingOrderState | None = None,
        processing_state: BorrowingOrderProcessingState | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BorrowingOrders]:
        """List a tenant's orders, newest first.

        ``state`` filters the local lifecycle (N1's staff list);
        ``processing_state`` filters by whether the order's effects completed,
        which is what the attention list needs.
        """
        statement = select(BorrowingOrders).where(
            BorrowingOrders.tenant_id == tenant_id
        )
        if state is not None:
            statement = statement.where(BorrowingOrders.state == state.value)
        if processing_state is not None:
            statement = statement.where(
                BorrowingOrders.processing_state == processing_state.value
            )
        statement = (
            statement.order_by(BorrowingOrders.created_at.desc(), BorrowingOrders.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_by_tenant(
        self,
        *,
        tenant_id: UUID,
        state: BorrowingOrderState | None = None,
        processing_state: BorrowingOrderProcessingState | None = None,
    ) -> int:
        """Count a tenant's orders under the same filters as ``get_by_tenant``."""
        statement = select(func.count()).select_from(BorrowingOrders).where(
            BorrowingOrders.tenant_id == tenant_id
        )
        if state is not None:
            statement = statement.where(BorrowingOrders.state == state.value)
        if processing_state is not None:
            statement = statement.where(
                BorrowingOrders.processing_state == processing_state.value
            )
        result = await self._session.execute(statement)
        return int(result.scalar_one())

    async def get_by_lf_number(
        self, *, tenant_id: UUID, lf_number: str
    ) -> BorrowingOrders | None:
        """Return the order claiming a Libris reference, or None.

        At most one order can claim a given ``lf_number``: the partial unique
        index ``borrowing_orders_lf_number_uq`` enforces it.
        """
        result = await self._session.execute(
            select(BorrowingOrders).where(
                BorrowingOrders.tenant_id == tenant_id,
                BorrowingOrders.libris_lf_number == lf_number,
            )
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        order_id: UUID,
        tenant_id: UUID,
        request_type: str,
        bibliographic: dict[str, Any],
        patron_barcode: str,
        patron_name: str,
        folio_user_status: str,
        folio_user_id: UUID | None = None,
        libris_lf_number: str | None = None,
    ) -> BorrowingOrders | None:
        """Insert an order, or return None when that id is already taken.

        ``state`` and ``processing_state`` are left to their column defaults
        (``SUBMITTED`` / ``UNHANDLED``).

        ``libris_lf_number`` is optional: pass it when the Libris request
        already exists, leave it None for the normal A5 case where a
        librarian records it later.

        None means the primary key conflicted. Deciding what that means --
        an idempotent re-submit, or an id belonging to another tenant -- is
        the service's job, not this one's.

        Raises ``IntegrityError`` when ``libris_lf_number`` is already
        claimed by another order; the partial unique index
        ``borrowing_orders_lf_number_uq`` enforces that. Callers must run
        this inside a savepoint if they intend to recover.
        """
        statement = (
            insert(BorrowingOrders)
            .values(
                id=order_id,
                tenant_id=tenant_id,
                request_type=request_type,
                bibliographic=bibliographic,
                patron_barcode=patron_barcode,
                patron_name=patron_name,
                folio_user_status=folio_user_status,
                folio_user_id=folio_user_id,
                libris_lf_number=libris_lf_number,
            )
            .on_conflict_do_nothing(constraint="borrowing_orders_pkey")
            .returning(BorrowingOrders)
        )
        result = await self._session.execute(statement)
        return result.scalars().one_or_none()

    async def set_libris_lf_number(
        self, *, tenant_id: UUID, order_id: UUID, libris_lf_number: str | None
    ) -> bool:
        """Record the Libris reference on an order. False when no row matched.

        Does not touch ``state``. Recording a reference is a claim about what
        a human typed; the link itself is ``ill_requests.borrowing_order_id``,
        resolved against the Libris record, and only that moves the order to
        ``LINKED``.

        Raises ``IntegrityError`` when another order already claims the
        reference. Callers must run this inside a savepoint if they intend to
        recover.
        """
        return await self.update(
            tenant_id=tenant_id,
            order_id=order_id,
            libris_lf_number=libris_lf_number,
        )

    async def update(
        self, *, tenant_id: UUID, order_id: UUID, **values: Any
    ) -> bool:
        """Update an order's columns. Returns False when no row matched.

        ``updated_at`` is bumped here because no database trigger maintains
        it (checked across all migrations), so an update that forgot it would
        leave the N1 "datum senast uppdaterad" column silently stale.
        """
        if not values:
            return False
        result = await self._session.execute(
            sql_update(BorrowingOrders)
            .where(
                BorrowingOrders.tenant_id == tenant_id,
                BorrowingOrders.id == order_id,
            )
            .values(**values, updated_at=func.now())
        )
        return result.rowcount == 1

    async def delete(self, *, tenant_id: UUID, order_id: UUID) -> bool:
        """Delete an order. Returns False when no row matched.

        Fails while comments or queued effects still reference the order:
        both carry a foreign key to ``(tenant_id, id)`` with no cascade.
        """
        result = await self._session.execute(
            sql_delete(BorrowingOrders).where(
                BorrowingOrders.tenant_id == tenant_id,
                BorrowingOrders.id == order_id,
            )
        )
        return result.rowcount == 1

    # ------------------------------------------------------------------
    # Effects owned by an order
    # ------------------------------------------------------------------

    async def insert_effect(
        self,
        *,
        tenant_id: UUID,
        borrowing_order_id: UUID,
        kind: str,
        effect_key: str,
        payload: dict[str, Any],
    ) -> None:
        """Persist one ``effect_queue`` row whose subject is a borrowing order.

        The subject is polymorphic: ``subject_type = 'BORROWING_ORDER'`` and
        ``subject_id`` is the order id. At A5 no ill_request exists yet, so the
        order is the only thing to point at.

        ``ON CONFLICT DO NOTHING`` on ``(tenant_id, effect_key)`` makes a
        repeated call unable to queue the same effect twice.
        """
        await self._session.execute(
            insert(EffectQueue)
            .values(
                id=uuid4(),
                tenant_id=tenant_id,
                subject_type=IllSubjectType.BORROWING_ORDER.value,
                subject_id=borrowing_order_id,
                kind=kind,
                effect_key=effect_key,
                payload=payload,
            )
            .on_conflict_do_nothing(constraint="effect_queue_tenant_id_effect_key_key")
        )
