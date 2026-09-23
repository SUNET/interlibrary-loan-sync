"""Admin endpoint -- periodic (``@app.periodic``) scheduling bookkeeping."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from ill_bridge.database.session import get_db
from ill_bridge.jobs.worker import app as procrastinate_app
from ill_bridge.repositories.procrastinate import ProcrastinateRepository
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_repo = ProcrastinateRepository()


@router.get("/scheduler")
async def get_scheduler_state(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Registered periodic tasks + last defer per (task, periodic_id).

    Cross-references Procrastinate's registry (in-process) with the
    ``procrastinate_periodic_defers`` table (durable). A registered task
    with no recent defer row means the periodic loop is not running --
    likely no worker process alive.
    """
    registered = [
        {
            "task_name": pt.task.name,
            "periodic_id": pt.periodic_id,
            "cron": pt.cron,
            "queue": pt.task.queue,
        }
        for pt in procrastinate_app.periodic_registry.periodic_tasks.values()
    ]
    defers = await _repo.list_periodic_defers(db)
    return {"registered": registered, "recent_defers": defers}
