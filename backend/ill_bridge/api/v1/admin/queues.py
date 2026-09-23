"""Admin endpoints -- queue depth, lag, and per-queue job listings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.procrastinate import ProcrastinateRepository

router = APIRouter()

_repo = ProcrastinateRepository()


@router.get("/queues")
async def list_queues(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Depth by (queue, status) plus oldest waiting job per queue.

    Two independent aggregations returned together so the admin UI can
    render both cards in one request.
    """
    depth = await _repo.queue_stats(db)
    oldest = await _repo.oldest_waiting(db)
    return {"depth": depth, "oldest_waiting": oldest}


@router.get("/queues/{queue}/jobs")
async def list_queue_jobs(
    queue: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await _repo.list_queue_jobs(db, queue=queue, limit=limit)
