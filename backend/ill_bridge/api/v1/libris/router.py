"""Libris router -- unifies resource sub-routers under ``/libris``."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from ill_bridge.api.v1.libris.effect_queue import router as effect_queue_router
from ill_bridge.api.v1.libris.ill_requests import router as ill_requests_router
from ill_bridge.api.v1.libris.providers import router as providers_router
from ill_bridge.api.v1.libris.raw_provider_requests import (
    router as raw_provider_requests_router,
)
from ill_bridge.api.v1.libris.request_parties import (
    router as request_parties_router,
)
from ill_bridge.api.v1.libris.state_audit_logs import (
    router as state_audit_logs_router,
)
from ill_bridge.api.v1.libris.tenants import router as tenants_router
from ill_bridge.dependencies.auth import require_admin

router = APIRouter(
    prefix="/libris",
    tags=["libris"],
    dependencies=[Depends(require_admin)],
)


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint for the Libris adapter."""
    return {"status": "ok"}


@router.get("/config")
async def get_config() -> dict[str, str]:
    """Get the configuration for the Libris adapter."""
    return {"config": "This is a placeholder for the Libris adapter configuration."}


router.include_router(tenants_router)
router.include_router(providers_router)
router.include_router(raw_provider_requests_router)
router.include_router(ill_requests_router)
router.include_router(effect_queue_router)
router.include_router(request_parties_router)
router.include_router(state_audit_logs_router)
