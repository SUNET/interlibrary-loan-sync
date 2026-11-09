"""Admin endpoint -- periodic (``@app.periodic``) scheduling bookkeeping."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ill_bridge.dependencies.jobs import get_procrastinate_service
from ill_bridge.services.procrastinate import ProcrastinateService

router = APIRouter()


@router.get("/scheduler")
async def get_scheduler_state(
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> dict[str, Any]:
    """Registered periodic tasks + last defer per (task, periodic_id).

    Cross-references Procrastinate's registry (in-process) with the
    ``procrastinate_periodic_defers`` table (durable). A registered task
    with no recent defer row means the periodic loop is not running --
    likely no worker process alive.
    """
    return await service.get_scheduler_state()
