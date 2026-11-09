"""Admin endpoints -- Procrastinate jobs (read + operations).

Everything goes through :class:`ProcrastinateService`: the service composes
the reads (delegating SELECTs to ``ProcrastinateRepository``) and runs the
mutations through ``app.job_manager`` -- never raw UPDATEs. This router only
translates service outcomes into HTTP responses.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from ill_bridge.dependencies.jobs import get_procrastinate_service
from ill_bridge.schemas.response.procrastinate import (
    CancelRequest,
    EnqueueRequest,
    RetryRequest,
)
from ill_bridge.services.procrastinate import (
    InvalidJobStatus,
    JobNotFoundError,
    ProcrastinateService,
)

router = APIRouter()


@router.get("/jobs")
async def list_jobs(
    status: str | None = None,
    queue: str | None = None,
    task_name: str | None = None,
    limit: int = 50,
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> list[dict[str, Any]]:
    """List Procrastinate jobs.

    Procrastinate only sets ``scheduled_at`` when a job is deferred for later
    via ``.configure(schedule_at=...)`` / ``schedule_in=...``. Plain
    ``defer_async()`` (immediate) leaves it NULL -- the worker picks it up ASAP
    based on id order. Jobs enqueued through ``POST /admin/jobs/{task}/run``
    use immediate defer, so NULL is expected.

    Rule:
    - ``scheduled_at IS NULL`` -> "run now"
    - ``scheduled_at IS NOT NULL`` -> "not before this timestamp"
    """
    try:
        return await service.list_jobs(
            status=status,
            queue=queue,
            task_name=task_name,
            limit=limit,
        )
    except InvalidJobStatus as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/jobs/failed")
async def list_failed_jobs(
    limit: int = 20,
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> list[dict[str, Any]]:
    return await service.list_failed_jobs(limit=limit)


@router.get("/jobs/running")
async def list_running_jobs(
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> list[dict[str, Any]]:
    return await service.list_running_jobs()


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> dict[str, Any]:
    try:
        return await service.get_job_required(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(404, "Job not found") from exc


@router.get("/jobs/{job_id}/events")
async def get_job_events(
    job_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> list[dict[str, Any]]:
    """Return the latest lifecycle transitions, newest first (not task logs)."""
    try:
        return await service.get_job_events(job_id, limit=limit)
    except JobNotFoundError as exc:
        raise HTTPException(404, "Job not found") from exc


# ---------- Operations ----------------------------------------------------


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel_job(
    job_id: int,
    body: CancelRequest | None = None,
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> dict[str, Any]:
    abort = bool(body and body.abort)
    try:
        await service.cancel_job(job_id, abort=abort)
    except JobNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"job_id": job_id, "cancelled": True, "abort_requested": abort}


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(
    job_id: int,
    body: RetryRequest | None = None,
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> dict[str, Any]:
    body = body or RetryRequest()
    try:
        await service.retry_job(
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
    service: ProcrastinateService = Depends(get_procrastinate_service),
) -> dict[str, Any]:
    body = body or EnqueueRequest()
    try:
        job_id = await service.enqueue_task(
            task_name,
            kwargs=body.kwargs,
            queue=body.queue,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"task_name": task_name, "job_id": job_id, "queued": True}
