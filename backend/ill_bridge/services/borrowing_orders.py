"""Borrowing order logic (A5).

Composition lives here; SQL lives in
:class:`~ill_bridge.repositories.borrowing_orders.BorrowingOrderRepository`.
This layer owns the rules: what must happen before an order is written, and
what the order owes once it exists.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID, uuid4

from ill_bridge.common.effects import EffectKind
from ill_bridge.common.enums import RequestType
from ill_bridge.common.exceptions import LibrisReferenceInUse, TenantMismatch
from ill_bridge.common.folio_client import FolioApiClient
from ill_bridge.common.states import (
    BorrowingOrderProcessingState,
    BorrowingOrderState,
)
from ill_bridge.database.models import BorrowingOrders
from ill_bridge.folio.users import PatronLookup, find_patron
from ill_bridge.repositories.borrowing_orders import BorrowingOrderRepository
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

# Effects owed by a newly created order (A5). Exactly one: the infodisk mail.
# Everything from A6 onward hangs off the linked ill_request instead, so this
# does not need the declarative planner in common/effects.py -- that one is
# keyed on provider observations and workflow transitions an order does not
# have.
ORDER_CREATED_EFFECTS: tuple[EffectKind, ...] = (EffectKind.NOTIFY_INFODISK,)


class BorrowingOrderService:
    """Business rules for local borrowing orders."""

    def __init__(
        self,
        repository: BorrowingOrderRepository,
        *,
        folio_client: FolioApiClient | None = None,
    ) -> None:
        self.repository = repository
        self._folio_client = folio_client

    async def list_orders(
        self,
        *,
        tenant_id: UUID,
        processing_state: BorrowingOrderProcessingState | None = None,
        linked: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[BorrowingOrders]:
        """List borrowing orders for a tenant, filtered by processing_state and/or linked."""
        return await self.repository.get_by_tenant(
            tenant_id=tenant_id,
            processing_state=processing_state,
            linked=linked,
            limit=limit,
            offset=offset,
        )

    async def create_order(
        self,
        *,
        tenant_id: UUID,
        request_type: RequestType,
        bibliographic: dict[str, Any],
        patron_barcode: str,
        patron_name: str,
        order_id: UUID | None = None,
        libris_lf_number: str | None = None,
    ) -> tuple[BorrowingOrders, bool]:
        """Run the A5 intake steps and return ``(order, created)``.

        In order:

        1. Look the patron up in FOLIO. This runs **before** the write
           because its outcome is a column on the order and is quoted in the
           infodisk mail. It never raises and never blocks: an order is
           created whatever FOLIO says.
        2. Insert the order.
        3. Queue the effects a new order owes.

        Steps 2 and 3 are in the caller's transaction, so an order cannot be
        committed without the infodisk mail being owed, and a rolled-back
        order cannot leave a mail behind. This mirrors ``apply_observation``
        on the polling side, which also writes a state change and its effects
        together instead of trusting the caller to remember.

        ``libris_lf_number`` is optional. Leave it None for the normal A5
        flow, where the Libris request does not exist yet and a librarian
        records the reference afterwards via :meth:`set_libris_lf_number`.
        Pass it when the Libris request already exists, to save the second
        call. Either way the order starts ``SUBMITTED``: a recorded
        reference is a claim, not a link.

        **Idempotency depends on who supplies the id.** With a caller-supplied
        ``order_id``, a repeated call returns the stored order with
        ``created=False`` and queues nothing, so no second mail is sent.
        Without one a fresh id is generated and every call creates a new
        order, so a retried POST means a duplicate order and a duplicate
        mail. Intake that can retry must supply the id.

        Raises :class:`LibrisReferenceInUse` when another order already
        claims the supplied reference.
        """
        patron = await self.check_patron(barcode=patron_barcode)

        order_id = order_id or uuid4()
        created = await self._create_guarded(
            order_id=order_id,
            tenant_id=tenant_id,
            request_type=request_type.value,
            bibliographic=bibliographic,
            patron_barcode=patron_barcode,
            patron_name=patron_name,
            folio_user_status=patron.status.value,
            folio_user_id=patron.folio_user_id,
            libris_lf_number=libris_lf_number,
        )

        if created is None:
            # The primary key conflicted. Either this is a re-submit of an
            # order we already hold, or the caller supplied an id belonging
            # to another tenant -- the key is global, so both are possible.
            existing = await self.repository.get(
                tenant_id=tenant_id, order_id=order_id
            )
            if existing is None:
                raise TenantMismatch(
                    f"borrowing order {order_id} exists but is not visible for "
                    f"tenant {tenant_id}; check app.tenant_id and the supplied "
                    f"order id"
                )
            # First write wins; a re-submit's values are discarded.
            return existing, False

        for effect_kind in ORDER_CREATED_EFFECTS:
            await self.add_effect(order=created, effect_kind=effect_kind)

        return created, True

    async def set_libris_lf_number(
        self,
        *,
        tenant_id: UUID,
        order_id: UUID,
        libris_lf_number: str | None,
    ) -> BorrowingOrders:
        """Record, correct or clear the Libris reference on an existing order.

        This is step 5 of the A6 linking sequence: a librarian creates the
        request by hand in Libris, Libris returns an ``lf_number``, and the
        librarian brings it back here. It is also how a typo gets corrected,
        and how a re-order after ``notfullfilled`` records its new reference.

        The order's ``state`` is untouched. Only resolving the reference
        against the Libris record, which sets
        ``ill_requests.borrowing_order_id``, makes an order ``LINKED``.

        Raises :class:`BorrowingOrderNotFound` when the order does not exist
        and :class:`LibrisReferenceInUse` when another order already claims
        the reference.
        """
        order = await self.repository.get_required(
            tenant_id=tenant_id, order_id=order_id
        )
        if order.libris_lf_number == libris_lf_number:
            return order

        await self._guard_reference_free(
            tenant_id=tenant_id,
            libris_lf_number=libris_lf_number,
            allow_order_id=order_id,
        )
        try:
            async with self.repository.savepoint():
                await self.repository.set_libris_lf_number(
                    tenant_id=tenant_id,
                    order_id=order_id,
                    libris_lf_number=libris_lf_number,
                )
        except IntegrityError as exc:
            # Lost a race with a concurrent claim between the check above and
            # this write. The index is the real arbiter, so report the same
            # failure rather than retrying.
            raise LibrisReferenceInUse(str(libris_lf_number)) from exc

        logger.info(
            "borrowing order %s libris reference set to %r",
            order_id,
            libris_lf_number,
        )
        return await self.repository.get_required(
            tenant_id=tenant_id, order_id=order_id
        )

    async def _create_guarded(
        self, *, libris_lf_number: str | None, **values: Any
    ) -> BorrowingOrders | None:
        """Insert, converting a duplicate reference into a typed error."""
        if libris_lf_number is not None:
            await self._guard_reference_free(
                tenant_id=values["tenant_id"], libris_lf_number=libris_lf_number
            )
        try:
            async with self.repository.savepoint():
                return await self.repository.create(
                    libris_lf_number=libris_lf_number, **values
                )
        except IntegrityError as exc:
            raise LibrisReferenceInUse(str(libris_lf_number)) from exc

    async def _guard_reference_free(
        self,
        *,
        tenant_id: UUID,
        libris_lf_number: str | None,
        allow_order_id: UUID | None = None,
    ) -> None:
        """Refuse a reference another order already claims.

        The partial unique index is what actually enforces this; checking
        first only buys a clear error instead of a constraint violation.
        """
        if libris_lf_number is None:
            return
        holder = await self.repository.get_by_lf_number(
            tenant_id=tenant_id, lf_number=libris_lf_number
        )
        if holder is not None and holder.id != allow_order_id:
            raise LibrisReferenceInUse(libris_lf_number, holder.id)

    async def check_patron(self, *, barcode: str) -> PatronLookup:
        """Look the patron up in FOLIO, never raising.

        Separate from :meth:`create_order` so the endpoint can show a patron
        verdict before anything is written, and so the check can be re-run
        later for an order stored as ``NOT_FOUND`` or ``CHECK_FAILED``.
        """
        return await find_patron(self._folio_client, barcode=barcode)

    async def add_effect(
        self,
        *,
        order: BorrowingOrders,
        effect_kind: EffectKind,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Queue one effect whose subject is this order.

        Derives the idempotency key and the payload, then hands both to the
        repository to persist.

        The payload carries no patron data. ``effect_queue.payload`` is
        unredacted JSONB, unlike ``state_audit_logs.details_redacted``, so
        the handler reads the order row rather than being handed a rendered
        mail body.
        """
        await self.repository.insert_effect(
            tenant_id=order.tenant_id,
            borrowing_order_id=order.id,
            kind=effect_kind.value,
            effect_key=self.effect_key(order=order, effect_kind=effect_kind),
            payload={"from": None, "to": order.state, **(context or {})},
        )

    @staticmethod
    def effect_key(*, order: BorrowingOrders, effect_kind: EffectKind) -> str:
        """Idempotency key for an order-owned effect.

        Same shape as the ill_request side
        (``{subject}:{state}:{kind}``), so ``UNIQUE (tenant_id, effect_key)``
        keeps one effect per subject per state across both subject types.
        """
        return f"{order.id}:{order.state}:{effect_kind.value}"

    async def cancel_order(
        self, *, tenant_id: UUID, order_id: UUID, reason: str | None = None
    ) -> bool:
        """Cancel an order that has not been sent to Libris yet.

        Refuses once the order is linked: from that point the Libris request
        is the thing that exists, and cancelling it is an A13 concern with
        FOLIO cleanup attached, not a local state flip.
        """
        order = await self.repository.get_required(
            tenant_id=tenant_id, order_id=order_id
        )
        if order.state == BorrowingOrderState.LINKED.value:
            logger.warning(
                "refusing to cancel linked borrowing order %s", order_id
            )
            return False
        if order.state == BorrowingOrderState.CANCELLED.value:
            return True
        return await self.repository.update(
            tenant_id=tenant_id,
            order_id=order_id,
            state=BorrowingOrderState.CANCELLED.value,
        )
