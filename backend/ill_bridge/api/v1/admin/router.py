"""Admin router -- Procrastinate control panel.

Prefix ``/admin`` lives ONLY on this router. Child routers must not set
their own prefix; that was the bug in the old file (``/admin/admin/jobs``).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from ill_bridge.api.v1.admin.jobs import router as jobs_router
from ill_bridge.api.v1.admin.queues import router as queues_router
from ill_bridge.api.v1.admin.scheduler import router as scheduler_router
from ill_bridge.api.v1.admin.workers import router as workers_router
from ill_bridge.dependencies.auth import require_admin

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)
router.include_router(jobs_router)
router.include_router(queues_router)
router.include_router(workers_router)
router.include_router(scheduler_router)


@router.get("/user", summary="Test the admin user credentials")
async def user(admin_user: str = Depends(require_admin)) -> dict[str, str]:
    """Test the admin user credentials."""
    return {"user": admin_user}
