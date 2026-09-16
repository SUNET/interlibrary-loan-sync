# api/v1/bgp/router.py
from fastapi import APIRouter

from api.v1.admin.jobs import router as jobs_router
from api.v1.admin.scheduler import router as scheduler_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(jobs_router)
router.include_router(scheduler_router)


@router.get(
    "/list",
    summary="-",
    description="-",
)
async def list_metrics():
    pass
