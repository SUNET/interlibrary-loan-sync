"""Admin endpoints -- queue depth, lag, and per-queue job listings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ill_bridge.dependencies.jobs import get_procrastinate_service
from ill_bridge.services.procrastinate import ProcrastinateService

router = APIRouter()


@router.get("/queues")
async def list_queues(
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> dict[str, Any]:
    """Depth by (queue, status) plus oldest waiting job per queue.

    Two independent aggregations returned together so the admin UI can
    render both cards in one request.
    """
    return await service.get_queue_overview()


@router.get("/queues/{queue}/jobs")
async def list_queue_jobs(
    queue: str,
    limit: int = 50,
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> list[dict[str, Any]]:
    return await service.list_queue_jobs(queue, limit=limit)
