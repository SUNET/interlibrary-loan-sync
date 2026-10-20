"""Admin endpoints -- Procrastinate jobs (read + operations).

Reads go through :class:`ProcrastinateRepository` (raw SELECTs on the
``procrastinate_*`` tables). Mutations go through
:class:`ProcrastinateService` (``app.job_manager``) -- never raw UPDATEs.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from ill_bridge.database.models.procrastinate import ProcrastinateJobStatus
from ill_bridge.database.session import get_db
from ill_bridge.jobs.worker import app as procrastinate_app
from ill_bridge.repositories.procrastinate import (
    ProcrastinateRepository,
)
from ill_bridge.schemas.response.procrastinate import (
    CancelRequest,
    EnqueueRequest,
    RetryRequest,
)
from ill_bridge.services.procrastinate import (
    JobNotFoundError,
    ProcrastinateService,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

_repo = ProcrastinateRepository()
_service = ProcrastinateService(procrastinate_app)


@router.get("/jobs")
async def list_jobs(
    status: str | None = None,
    queue: str | None = None,
    task_name: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List Procrastinate jobs.

    Args:
        status (str | None, optional): _description_. Defaults to None.
        queue (str | None, optional): _description_. Defaults to None.
        task_name (str | None, optional): _description_. Defaults to None.
        limit (int, optional): _description_. Defaults to 50.
        db (AsyncSession, optional): _description_. Defaults to Depends(get_db).

    Raises:
        HTTPException: _description_

    Returns:
        list[dict[str, Any]]: _description_
    Procrastinate only sets scheduled_at when a job is deferred for later via .configure(schedule_at=...) / schedule_in=.... Plain defer_async() (immediate) leaves it NULL — the worker picks it up ASAP based on id order. All your jobs above were enqueued through POST /admin/jobs/{task}/run → immediate defer → NULL is correct.
    Rule:
    - scheduled_at IS NULL → "run now"
    - scheduled_at IS NOT NULL → "not before this timestamp"

    """
    if status is not None and status not in ProcrastinateJobStatus.__members__:
        raise HTTPException(
            422,
            f"Unknown status; expected one of {list(ProcrastinateJobStatus.__members__.keys())}",
        )
    return await _repo.list_jobs(
        db,
        status=status,
        queue=queue,
        task_name=task_name,
        limit=limit,
    )


@router.get("/jobs/failed")
async def list_failed_jobs(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await _repo.list_failed_jobs(db, limit=limit)


@router.get("/jobs/running")
async def list_running_jobs(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    return await _repo.list_running_jobs(db)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    job = await _repo.get_job(db, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs/{job_id}/events")
async def get_job_events(
    job_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return the latest lifecycle transitions, newest first (not task logs)."""
    if await _repo.get_job(db, job_id) is None:
        raise HTTPException(404, "Job not found")
    return await _repo.get_job_events(db, job_id, limit=limit)


# ---------- Operations ----------------------------------------------------


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel_job(
    job_id: int,
    body: CancelRequest | None = None,
) -> dict[str, Any]:
    abort = bool(body and body.abort)
    try:
        await _service.cancel_job(job_id, abort=abort)
    except JobNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"job_id": job_id, "cancelled": True, "abort_requested": abort}


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(
    job_id: int,
    body: RetryRequest | None = None,
) -> dict[str, Any]:
    body = body or RetryRequest()
    try:
        await _service.retry_job(
            job_id,
            priority=body.priority,
            queue=body.queue,
            lock=body.lock,
        )
    except Exception as exc:  # procrastinate raises various types
        raise HTTPException(400, f"Retry failed: {exc}") from exc
    return {"job_id": job_id, "retried": True}


# NOTE: {task_name} not {job_id} -- this enqueues a *new* run of a task.
@router.post("/jobs/{task_name}/run", status_code=202)
async def run_task(
    task_name: str,
    body: EnqueueRequest | None = None,
) -> dict[str, Any]:
    body = body or EnqueueRequest()
    try:
        job_id = await _service.enqueue_task(
            task_name,
            kwargs=body.kwargs,
            queue=body.queue,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"task_name": task_name, "job_id": job_id, "queued": True}
