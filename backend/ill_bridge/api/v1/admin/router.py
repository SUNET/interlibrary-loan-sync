"""Admin router -- Procrastinate control panel.

Prefix ``/admin`` lives ONLY on this router. Child routers must not set
their own prefix; that was the bug in the old file (``/admin/admin/jobs``).
"""
from __future__ import annotations

from fastapi import APIRouter

from ill_bridge.api.v1.admin.jobs import router as jobs_router
from ill_bridge.api.v1.admin.queues import router as queues_router
from ill_bridge.api.v1.admin.scheduler import router as scheduler_router
from ill_bridge.api.v1.admin.workers import router as workers_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(jobs_router)
router.include_router(queues_router)
router.include_router(workers_router)
router.include_router(scheduler_router)
