from fastapi import Depends
from ill_bridge.database.session import get_db
from ill_bridge.repositories.procrastinate import ProcrastinateRepository
from ill_bridge.services.procrastinate import ProcrastinateService
from sqlalchemy.ext.asyncio import AsyncSession


def get_procrastinate_service(
    session: AsyncSession = Depends(get_db),
) -> ProcrastinateService:
    """Provide the Procrastinate service for the admin API.

    Assembles the service from a request-scoped repository (reads, bound to
    the request session) and the Procrastinate ``App`` (mutations via
    ``app.job_manager``). The worker is imported lazily to avoid loading
    worker configuration during FastAPI application import.
    """
    from ill_bridge.jobs.bootstrap import app as procrastinate_app

    return ProcrastinateService(
        ProcrastinateRepository(session),
        procrastinate_app,
    )
