"""Admin router -- Procrastinate control panel.

Prefix ``/admin`` lives ONLY on this router. Child routers must not set
their own prefix; that was the bug in the old file (``/admin/admin/jobs``).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ill_bridge.database.session import get_db
from ill_bridge.repositories.provider import ProviderRepository


# from ill_bridge.api.v1.admin.jobs import router as jobs_router

router = APIRouter(prefix="/libris", tags=["libris"])

# router.include_router(jobs_router)


@router.get("/health")
async def health_check():
    """Health check endpoint for the Libris adapter."""
    return {"status": "ok"}


@router.get("/config")
async def get_config():
    """Get the configuration for the Libris adapter."""
    return {"config": "This is a placeholder for the Libris adapter configuration."}


@router.get("/providers")
async def get_provider(
    session: AsyncSession = Depends(get_db),
):
    repository = ProviderRepository(session)

    providers = await repository.list()

    return [
        {
            "id": str(provider.id),
            "name": provider.display_name,
            "adapter_key": provider.adapter_key,
            "enabled": provider.enabled,
        }
        for provider in providers
    ]


@router.get("/providers/{provider_id}")
async def get_provider(
    provider_id: UUID,
    session: AsyncSession = Depends(get_db),
):
    repository = ProviderRepository(session)

    provider = await repository.get(provider_id)

    if provider is None:
        return {"error": "Provider not found"}

    return {
        "id": str(provider.id),
        "name": provider.display_name,
        "adapter_key": provider.adapter_key,
        "enabled": provider.enabled,
    }
