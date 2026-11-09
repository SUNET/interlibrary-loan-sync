"""Admin endpoint -- registered Procrastinate workers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ill_bridge.dependencies.jobs import get_procrastinate_service
from ill_bridge.services.procrastinate import ProcrastinateService

router = APIRouter()


@router.get("/workers")
async def list_workers(
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> list[dict[str, Any]]:
    """Workers currently known to Procrastinate.

    The table is heartbeated. A stale ``last_heartbeat`` on a worker that
    also owns a ``doing`` job in ``procrastinate_jobs`` is the classic
    zombie-worker signature -- the admin UI colours those red.
    """
    return await service.list_workers()
