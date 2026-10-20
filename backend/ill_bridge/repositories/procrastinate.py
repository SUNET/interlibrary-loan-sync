from __future__ import annotations

from enum import Enum
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.models.procrastinate import (
    ProcrastinateEvents,
    ProcrastinateJobEventType,
    ProcrastinateJobs,
    ProcrastinateJobStatus,
    ProcrastinatePeriodicDefers,
    ProcrastinateWorkers,
)

JOB_STATUSES: tuple[str, ...] = tuple(status.value for status in ProcrastinateJobStatus)


def _value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _rows(result: Any) -> list[dict[str, Any]]:
    return [
        {key: _value(value) for key, value in row.items()}
        for row in result.mappings().all()
    ]


class ProcrastinateRepository:
    async def list_jobs(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        queue: str | None = None,
        task_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        stmt = select(
            ProcrastinateJobs.id,
            ProcrastinateJobs.queue_name,
            ProcrastinateJobs.task_name,
            ProcrastinateJobs.priority,
            ProcrastinateJobs.status,
            ProcrastinateJobs.scheduled_at,
            ProcrastinateJobs.attempts,
            ProcrastinateJobs.abort_requested,
            ProcrastinateJobs.worker_id,
        )
        if status:
            stmt = stmt.where(ProcrastinateJobs.status == status)
        if queue:
            stmt = stmt.where(ProcrastinateJobs.queue_name == queue)
        if task_name:
            stmt = stmt.where(ProcrastinateJobs.task_name == task_name)
        result = await session.execute(
            stmt.order_by(desc(ProcrastinateJobs.id)).limit(limit)
        )
        return _rows(result)

    async def get_job(
        self, session: AsyncSession, job_id: int
    ) -> dict[str, Any] | None:
        stmt = select(
            ProcrastinateJobs.id,
            ProcrastinateJobs.queue_name,
            ProcrastinateJobs.task_name,
            ProcrastinateJobs.priority,
            ProcrastinateJobs.lock,
            ProcrastinateJobs.args,
            ProcrastinateJobs.status,
            ProcrastinateJobs.scheduled_at,
            ProcrastinateJobs.attempts,
            ProcrastinateJobs.queueing_lock,
            ProcrastinateJobs.abort_requested,
            ProcrastinateJobs.worker_id,
        ).where(ProcrastinateJobs.id == job_id)
        row = (await session.execute(stmt)).mappings().first()
        return {key: _value(value) for key, value in row.items()} if row else None

    async def get_job_events(
        self, session: AsyncSession, job_id: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                ProcrastinateEvents.id,
                ProcrastinateEvents.job_id,
                ProcrastinateEvents.type,
                ProcrastinateEvents.at,
            )
            .where(ProcrastinateEvents.job_id == job_id)
            .order_by(desc(ProcrastinateEvents.id))
            .limit(limit)
        )
        return _rows(await session.execute(stmt))

    async def list_failed_jobs(
        self, session: AsyncSession, limit: int = 20
    ) -> list[dict[str, Any]]:
        stmt = (
            select(
                ProcrastinateJobs.id,
                ProcrastinateJobs.task_name,
                ProcrastinateJobs.args,
                ProcrastinateJobs.attempts,
                ProcrastinateJobs.scheduled_at,
            )
            .where(ProcrastinateJobs.status == ProcrastinateJobStatus.FAILED)
            .order_by(desc(ProcrastinateJobs.id))
            .limit(limit)
        )
        return _rows(await session.execute(stmt))

    async def list_running_jobs(self, session: AsyncSession) -> list[dict[str, Any]]:
        stmt = (
            select(
                ProcrastinateJobs.id,
                ProcrastinateJobs.queue_name,
                ProcrastinateJobs.task_name,
                ProcrastinateJobs.worker_id,
                ProcrastinateJobs.attempts,
                ProcrastinateJobs.scheduled_at,
            )
            .where(ProcrastinateJobs.status == ProcrastinateJobStatus.DOING)
            .order_by(asc(ProcrastinateJobs.id))
        )
        return _rows(await session.execute(stmt))

    async def list_queue_jobs(
        self, session: AsyncSession, queue: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        return await self.list_jobs(session, queue=queue, limit=limit)

    async def queue_stats(self, session: AsyncSession) -> list[dict[str, Any]]:
        stmt = (
            select(
                ProcrastinateJobs.queue_name,
                ProcrastinateJobs.status,
                func.count().label("count"),
            )
            .group_by(ProcrastinateJobs.queue_name, ProcrastinateJobs.status)
            .order_by(ProcrastinateJobs.queue_name, ProcrastinateJobs.status)
        )
        return _rows(await session.execute(stmt))

    async def oldest_waiting(self, session: AsyncSession) -> list[dict[str, Any]]:
        waiting_since = func.min(
            func.coalesce(ProcrastinateJobs.scheduled_at, ProcrastinateEvents.at)
        )
        oldest_seconds = func.extract("epoch", func.now() - waiting_since).label(
            "oldest_seconds"
        )
        stmt = (
            select(ProcrastinateJobs.queue_name, oldest_seconds)
            .join(
                ProcrastinateEvents,
                (ProcrastinateEvents.job_id == ProcrastinateJobs.id)
                & (ProcrastinateEvents.type == ProcrastinateJobEventType.DEFERRED),
            )
            .where(ProcrastinateJobs.status == ProcrastinateJobStatus.TODO)
            .group_by(ProcrastinateJobs.queue_name)
            .order_by(desc(oldest_seconds).nulls_last())
        )
        return _rows(await session.execute(stmt))

    async def list_workers(self, session: AsyncSession) -> list[dict[str, Any]]:
        heartbeat_age = func.extract(
            "epoch", func.now() - ProcrastinateWorkers.last_heartbeat
        ).label("heartbeat_age_seconds")
        doing_count = (
            func.count(ProcrastinateJobs.id)
            .filter(ProcrastinateJobs.status == ProcrastinateJobStatus.DOING)
            .label("doing_count")
        )
        stmt = (
            select(
                ProcrastinateWorkers.id,
                ProcrastinateWorkers.last_heartbeat,
                heartbeat_age,
                doing_count,
            )
            .outerjoin(
                ProcrastinateJobs,
                ProcrastinateJobs.worker_id == ProcrastinateWorkers.id,
            )
            .group_by(ProcrastinateWorkers.id, ProcrastinateWorkers.last_heartbeat)
            .order_by(desc(ProcrastinateWorkers.last_heartbeat).nulls_last())
        )
        return _rows(await session.execute(stmt))

    async def list_periodic_defers(self, session: AsyncSession) -> list[dict[str, Any]]:
        stmt = (
            select(
                ProcrastinatePeriodicDefers.id,
                ProcrastinatePeriodicDefers.task_name,
                ProcrastinatePeriodicDefers.periodic_id,
                ProcrastinatePeriodicDefers.defer_timestamp,
                ProcrastinatePeriodicDefers.job_id,
            )
            .order_by(desc(ProcrastinatePeriodicDefers.defer_timestamp))
            .limit(100)
        )
        return _rows(await session.execute(stmt))
