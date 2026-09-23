"""Admin endpoint -- registered Procrastinate workers."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.procrastinate import ProcrastinateRepository

router = APIRouter()

_repo = ProcrastinateRepository()


@router.get("/workers")
async def list_workers(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Workers currently known to Procrastinate.

    The table is heartbeated. A stale ``last_heartbeat`` on a worker that
    also owns a ``doing`` job in ``procrastinate_jobs`` is the classic
    zombie-worker signature -- the admin UI colours those red.
    """
    return await _repo.list_workers(db)
