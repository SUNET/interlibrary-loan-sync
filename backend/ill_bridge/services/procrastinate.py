"""Operational commands against Procrastinate.

Read state lives in :class:`ProcrastinateRepository`. Anything that mutates
job state -- retry, cancel, abort, enqueue -- goes through Procrastinate's
:class:`~procrastinate.manager.JobManager` instead of raw ``UPDATE`` on
``procrastinate_jobs``. Procrastinate models state transitions as SQL
functions (see ``procrastinate_cancel_job``, ``procrastinate_retry_job``),
so calling the manager is the only way to keep event history and locking
invariants intact.
"""
from __future__ import annotations

from typing import Any

from procrastinate import App
from procrastinate.exceptions import JobAborted
from ill_bridge.common.exceptions import JobNotFoundError



class ProcrastinateService:
    """Thin façade over ``App.job_manager`` for the admin API."""

    def __init__(self, app: App) -> None:
        self._app = app

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
    "JobAborted",
    "JobNotFoundError",
    "ProcrastinateService",
]
