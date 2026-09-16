import time
import traceback
from fastapi import APIRouter, HTTPException
from config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from fastapi import Depends
from core.dependencies import get_db


router = APIRouter()


from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.database import get_db
from ill_bridge.database.repository.procrastinate import (
    ProcrastinateRepository,
)


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

procrastinate_repo = ProcrastinateRepository()


@router.get("/jobs")
async def list_jobs(
    status: str | None = None,
    queue: str | None = None,
    task_name: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    return await procrastinate_repo.list_jobs(
        db,
        status=status,
        queue=queue,
        task_name=task_name,
        limit=limit,
    )


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    job = await procrastinate_repo.get_job(
        db,
        job_id,
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return job



@router.get("/jobs/{job_id}/events")
async def get_job_events(
    job_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await procrastinate_repo.get_job_events(
        db,
        job_id,
    )


@router.get("/jobs")
async def list_jobs(
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text("""
            SELECT
                id,
                task_name,
                queue,
                status,
                started_at,
                finished_at
            FROM procrastinate_jobs
            ORDER BY id DESC
            LIMIT 50
        """)
    )

    return [dict(row) for row in result.mappings().all()]
