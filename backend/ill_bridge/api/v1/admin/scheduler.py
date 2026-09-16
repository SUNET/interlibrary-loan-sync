import time
import traceback
from fastapi import APIRouter, HTTPException
from config import get_settings
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text
from fastapi import Depends
from core.dependencies import get_db


router = APIRouter()


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
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
                finished_at,
                attempts
            FROM procrastinate_jobs
            WHERE id = :job_id
        """),
        {
            "job_id": job_id,
        },
    )

    job = result.mappings().first()

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    return dict(job)
