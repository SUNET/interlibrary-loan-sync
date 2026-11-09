"""Procrastinate admin logic -- the single entry point for the admin API.

This layer owns everything the admin endpoints need and nothing the HTTP
layer should decide:

* **Reads** are composed here and delegated to
  :class:`~ill_bridge.repositories.procrastinate.ProcrastinateRepository`,
  which holds the raw SELECTs. Validation (is this a known status?) and
  "missing row" handling (raise :class:`JobNotFoundError`) live here, not in
  the router and not in the repository.
* **Mutations** -- retry, cancel, abort, enqueue -- go through
  Procrastinate's :class:`~procrastinate.manager.JobManager` rather than raw
  ``UPDATE`` on ``procrastinate_jobs``. Procrastinate models state
  transitions as SQL functions (see ``procrastinate_cancel_job``,
  ``procrastinate_retry_job``), so calling the manager is the only way to
  keep event history and locking invariants intact.

The service is constructed with a repository and the Procrastinate ``App``,
mirroring :class:`~ill_bridge.services.borrowing_orders.BorrowingOrderService`,
which is built from its repository.
"""
from __future__ import annotations

from typing import Any

from procrastinate import App
from procrastinate.exceptions import JobAborted

from ill_bridge.common.exceptions import InvalidJobStatus, JobNotFoundError
from ill_bridge.database.models.procrastinate import ProcrastinateJobStatus
from ill_bridge.repositories.procrastinate import ProcrastinateRepository


class ProcrastinateService:
    """Business logic for the admin control panel over Procrastinate."""

    def __init__(self, repository: ProcrastinateRepository, app: App) -> None:
        self._repository = repository
        self._app = app

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        queue: str | None = None,
        task_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List jobs, rejecting an unknown status before it hits the query."""
        if status is not None and status not in ProcrastinateJobStatus.__members__:
            raise InvalidJobStatus(
                "Unknown status; expected one of "
                f"{list(ProcrastinateJobStatus.__members__.keys())}"
            )
        return await self._repository.list_jobs(
            status=status,
            queue=queue,
            task_name=task_name,
            limit=limit,
        )

    async def list_failed_jobs(self, limit: int = 20) -> list[dict[str, Any]]:
        return await self._repository.list_failed_jobs(limit=limit)

    async def list_running_jobs(self) -> list[dict[str, Any]]:
        return await self._repository.list_running_jobs()

    async def get_job(self, job_id: int) -> dict[str, Any] | None:
        """Return one job, or None when it does not exist."""
        return await self._repository.get_job(job_id)

    async def get_job_required(self, job_id: int) -> dict[str, Any]:
        """Return one job, raising :class:`JobNotFoundError` when absent."""
        job = await self._repository.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id} not found")
        return job

    async def get_job_events(
        self, job_id: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Latest lifecycle transitions for a job, newest first.

        The job must exist: asking for the events of an unknown id is a
        not-found, not an empty list.
        """
        await self.get_job_required(job_id)
        return await self._repository.get_job_events(job_id, limit=limit)

    # ------------------------------------------------------------------
    # Queues
    # ------------------------------------------------------------------

    async def get_queue_overview(self) -> dict[str, Any]:
        """Depth by (queue, status) plus the oldest waiting job per queue.

        Two independent aggregations returned together so the admin UI can
        render both cards from one request.
        """
        return {
            "depth": await self._repository.queue_stats(),
            "oldest_waiting": await self._repository.oldest_waiting(),
        }

    async def list_queue_jobs(
        self, queue: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        return await self._repository.list_queue_jobs(queue, limit=limit)

    # ------------------------------------------------------------------
    # Workers & scheduler
    # ------------------------------------------------------------------

    async def list_workers(self) -> list[dict[str, Any]]:
        return await self._repository.list_workers()

    async def get_scheduler_state(self) -> dict[str, Any]:
        """Registered periodic tasks + last defer per (task, periodic_id).

        Cross-references Procrastinate's in-process registry with the durable
        ``procrastinate_periodic_defers`` table. A registered task with no
        recent defer row means the periodic loop is not running -- likely no
        worker process alive.
        """
        registered = [
            {
                "task_name": pt.task.name,
                "periodic_id": pt.periodic_id,
                "cron": pt.cron,
                "queue": pt.task.queue,
            }
            for pt in self._app.periodic_registry.periodic_tasks.values()
        ]
        defers = await self._repository.list_periodic_defers()
        return {"registered": registered, "recent_defers": defers}

    # ------------------------------------------------------------------
    # Job control
    # ------------------------------------------------------------------

    async def cancel_job(self, job_id: int, *, abort: bool = False) -> bool:
        """Cancel a job.

        * ``abort=False`` -- refuse to run a job that has not started yet.
        * ``abort=True``  -- request cooperative abort of a running job;
          the task must check ``JobContext.should_abort()`` for this to
          have any effect.

        Returns ``True`` when Procrastinate acknowledged the cancellation.
        """
        result = await self._app.job_manager.cancel_job_by_id_async(
            job_id,
            abort=abort,
        )
        if result is False:
            # Procrastinate returns False both for "unknown id" and "already
            # running when abort=False was requested". We can't distinguish
            # cheaply; surface as not-found and let the caller inspect state.
            raise JobNotFoundError(
                f"Job {job_id} cannot be cancelled (unknown or already running)"
            )
        return True

    async def retry_job(
        self,
        job_id: int,
        *,
        priority: int | None = None,
        queue: str | None = None,
        lock: str | None = None,
    ) -> None:
        """Requeue a failed job for another attempt."""
        await self._app.job_manager.retry_job_by_id_async(
            job_id,
            priority=priority,
            queue=queue,
            lock=lock,
        )

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    async def enqueue_task(
        self,
        task_name: str,
        *,
        kwargs: dict[str, Any] | None = None,
        queue: str | None = None,
    ) -> int:
        """Defer a task by name.

        Manual triggers from the admin UI go through here so the audit
        trail (``procrastinate_events``) shows *who* pressed the button
        -- see caller-side context in the API layer.
        """
        task = self._app.tasks.get(task_name)
        if task is None:
            raise LookupError(f"Unknown task: {task_name}")

        configured = task.configure(queue=queue) if queue else task
        job_id = await configured.defer_async(**(kwargs or {}))
        return job_id


__all__ = [
    "InvalidJobStatus",
    "JobAborted",
    "JobNotFoundError",
    "ProcrastinateService",
]
