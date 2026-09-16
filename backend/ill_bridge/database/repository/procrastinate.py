# ill_bridge/repositories/procrastinate.py

from flask import session
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ProcrastinateRepository:

    async def list_jobs(
        self,
        session: AsyncSession,
        status: str | None = None,
        queue: str | None = None,
        task_name: str | None = None,
        limit: int = 50,
    ) -> list[dict]:

        sql = """
            SELECT
                id,
                queue_name,
                task_name,
                priority,
                status,
                scheduled_at,
                attempts,
                abort_requested,
                worker_id
            FROM procrastinate_jobs
            WHERE 1 = 1
        """

        params = {
            "limit": limit,
        }

        if status:
            sql += " AND status = :status"
            params["status"] = status

        if queue:
            sql += " AND queue_name = :queue"
            params["queue"] = queue

        if task_name:
            sql += " AND task_name = :task_name"
            params["task_name"] = task_name

        sql += """
            ORDER BY id DESC
            LIMIT :limit
        """

        result = await session.execute(
            text(sql),
            params,
        )

        return [
            dict(row._mapping)
            for row in result
        ]
        
    async def get_job(
        self,
        session: AsyncSession,
        job_id: int,
    ) -> dict | None:

        result = await session.execute(
            text("""
                SELECT
                    id,
                    queue_name,
                    task_name,
                    priority,
                    lock,
                    args,
                    status,
                    scheduled_at,
                    attempts,
                    queueing_lock,
                    abort_requested,
                    worker_id
                FROM procrastinate_jobs
                WHERE id = :job_id
            """),
            {
                "job_id": job_id,
            },
        )

        row = result.first()

        if row is None:
            return None

        return dict(row._mapping)



    async def get_job_events(
        self,
        session: AsyncSession,
        job_id: int,
    ) -> list[dict]:

        result = await session.execute(
            text("""
                SELECT
                    id,
                    job_id,
                    type,
                    at
                FROM procrastinate_events
                WHERE job_id = :job_id
                ORDER BY at ASC
            """),
            {
                "job_id": job_id,
            },
        )

        return [
            dict(row._mapping)
            for row in result
        ]
