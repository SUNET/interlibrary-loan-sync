"""Borrowing (inlån) API — phase A, the local order.

A5 in ill_flow.md: the patron completes the form in discovery, an order is
written here, the infodisk is mailed, and the patron is looked up in FOLIO.

Nothing in this module talks to Libris. The Libris request is created by
hand by a librarian at A6, because the Libris ILL API has no
request-creation endpoint (api_doc.md:1083).
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.common.exceptions import (
    BorrowingOrderNotFound,
    LibrisReferenceInUse,
    TenantMismatch,
)
from ill_bridge.common.folio_client import get_folio_client
from ill_bridge.common.states import BorrowingOrderProcessingState
from ill_bridge.database.models import Tenants
from ill_bridge.database.session import get_db
from ill_bridge.dependencies.auth import ApiClientIdentity, get_current_client
from ill_bridge.repositories.borrowing_orders import BorrowingOrderRepository
from ill_bridge.schemas.request.borrowing import (
    BorrowingOrderCreate,
    BorrowingOrderUpdate,
)
from ill_bridge.schemas.response.borrowing import BorrowingOrderRead
from ill_bridge.services.borrowing_orders import BorrowingOrderService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/borrowing", tags=["borrowing"])


async def resolve_tenant(
    session: Annotated[AsyncSession, Depends(get_db)],
    identity: Annotated[ApiClientIdentity, Depends(get_current_client)],
    # x_tenant_id: Annotated[UUID | None, Header()] = None,
) -> Tenants:
    """Resolve the acting tenant and scope row-level security to it.

    PROVISIONAL. There is no authentication anywhere in ``api/`` yet, so this
    trusts a header. It is the smallest thing that makes RLS real on the API
    path; it is not an access control decision. Replace with the service API
    key from the discovery layer before this is reachable from outside
    (P0-4 / Q9).

    ``set_config(..., true)`` is the transaction-local form, so the setting
    dies with the request's transaction and cannot leak to the next request
    sharing the connection.
    """
    x_tenant_id: UUID | None = identity.tenant_id
    if x_tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-Id header is required",
        )

    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(x_tenant_id)},
    )

    tenant = (
        await session.execute(select(Tenants).where(Tenants.id == x_tenant_id))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown tenant {x_tenant_id}",
        )
    return tenant


def build_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenants, Depends(resolve_tenant)],
) -> BorrowingOrderService:
    """Assemble the service for this request.

    A FOLIO client that cannot be built is passed as None rather than raised:
    the patron check must never stop an order being created, so a
    misconfigured FOLIO becomes CHECK_FAILED on the order and a line in the
    infodisk mail.
    """
    try:
        folio_client = get_folio_client(tenant.folio_tenant_key)
    except Exception:
        logger.exception(
            "no FOLIO client for tenant %s; patron check will report "
            "CHECK_FAILED",
            tenant.folio_tenant_key,
        )
        folio_client = None

    return BorrowingOrderService(
        BorrowingOrderRepository(session),
        folio_client=folio_client,
    )


def _parse_processing_status(
    value: str | None,
) -> BorrowingOrderProcessingState | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    try:
        return BorrowingOrderProcessingState(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be 'handled' or 'unhandled'",
        ) from exc


@router.get(
    "/order",
    response_model=list[BorrowingOrderRead],
    summary="List borrowing orders for the acting tenant (N1)",
)
@router.get(
    "/orders",
    response_model=list[BorrowingOrderRead],
    include_in_schema=False,
)
async def list_borrowing_orders(
    tenant: Annotated[Tenants, Depends(resolve_tenant)],
    service: Annotated[BorrowingOrderService, Depends(build_service)],
    status_filter: Annotated[
        str | None,
        Query(
            alias="status",
            description="Filter by processing_state: handled | unhandled (case-insensitive).",
        ),
    ] = None,
    linked: Annotated[
        bool | None,
        Query(
            description="Filter by presence of libris_lf_number (true = set, false = null).",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BorrowingOrderRead]:
    """Return the tenant's borrowing orders, optionally filtered by ``status`` and ``linked``."""
    processing_state = _parse_processing_status(status_filter)
    orders = await service.list_orders(
        tenant_id=tenant.id,
        processing_state=processing_state,
        linked=linked,
        limit=limit,
        offset=offset,
    )
    return [BorrowingOrderRead.model_validate(order) for order in orders]


@router.post(
    "/orders",
    response_model=BorrowingOrderRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a borrowing order (A5)",
    responses={
        200: {"description": "Order already existed; nothing was created."},
        201: {"description": "Order created and the infodisk mail queued."},
    },
)
async def create_borrowing_order(
    payload: BorrowingOrderCreate,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenants, Depends(resolve_tenant)],
    service: Annotated[BorrowingOrderService, Depends(build_service)],
) -> BorrowingOrderRead:
    """Create an order, check the patron in FOLIO, and queue the infodisk mail.

    Returns **201** when an order was created and **200** when the supplied
    ``order_id`` already existed, so a caller retrying after a timeout can
    tell the two apart. A repeat does not queue a second mail.

    A patron missing from FOLIO does not fail the request: the outcome is
    recorded on the order and reported in the mail, per A5.
    """
    try:
        order, created = await service.create_order(
            tenant_id=tenant.id,
            request_type=payload.request_type,
            bibliographic=payload.bibliographic,
            patron_barcode=payload.patron_barcode,
            patron_name=payload.patron_name,
            order_id=payload.order_id,
            libris_lf_number=payload.libris_lf_number,
        )
    except TenantMismatch as exc:
        # The id is real but belongs elsewhere. Creating anything would be
        # wrong, and confirming whose it is would leak across tenants.
        logger.warning("borrowing order id conflict: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="order_id is already in use",
        ) from exc
    except LibrisReferenceInUse as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Libris reference {exc.lf_number!r} is already claimed "
            f"by another order",
        ) from exc

    # The order row and its queued effect commit together, or neither does.
    await session.commit()

    response.status_code = (
        status.HTTP_201_CREATED if created else status.HTTP_200_OK
    )
    return BorrowingOrderRead.model_validate(order)


@router.patch(
    "/orders/{order_id}",
    response_model=BorrowingOrderRead,
    summary="Record the Libris reference on an order (A6)",
    responses={
        404: {"description": "No such order for this tenant."},
        409: {"description": "Another order already claims that reference."},
    },
)
async def update_borrowing_order(
    order_id: UUID,
    payload: BorrowingOrderUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    tenant: Annotated[Tenants, Depends(resolve_tenant)],
    service: Annotated[BorrowingOrderService, Depends(build_service)],
) -> BorrowingOrderRead:
    """Record, correct or clear an order's Libris reference.

    Used after A6: the librarian creates the request by hand in Libris,
    Libris returns an ``lf_number``, and it is brought back here. The same
    call corrects a typo and records the new reference after a re-order.

    The order's ``state`` does not change. A recorded reference is a claim
    about what a human typed; the order becomes ``LINKED`` only once that
    reference is resolved against the Libris record.
    """
    try:
        order = await service.set_libris_lf_number(
            tenant_id=tenant.id,
            order_id=order_id,
            libris_lf_number=payload.libris_lf_number,
        )
    except BorrowingOrderNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Borrowing order {order_id} not found",
        ) from exc
    except LibrisReferenceInUse as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Libris reference {exc.lf_number!r} is already claimed "
            f"by another order",
        ) from exc

    await session.commit()
    return BorrowingOrderRead.model_validate(order)


@router.get(
    "/orders/{order_id}",
    response_model=BorrowingOrderRead,
    summary="Read one borrowing order (N1)",
)
async def get_borrowing_order(
    order_id: UUID,
    tenant: Annotated[Tenants, Depends(resolve_tenant)],
    service: Annotated[BorrowingOrderService, Depends(build_service)],
) -> BorrowingOrderRead:
    order = await service.repository.get(tenant_id=tenant.id, order_id=order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Borrowing order {order_id} not found",
        )
    return BorrowingOrderRead.model_validate(order)


@router.get("/order/identity", summary="Get user identity from access token")
async def get_identity(
    identity: Annotated[ApiClientIdentity, Depends(get_current_client)],
) -> dict[str, object]:
    return {
        "client_id": identity.client_id,
        "tenant_id": identity.tenant_id,
        "roles": sorted(identity.roles),
    }
