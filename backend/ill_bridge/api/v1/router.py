# ill_bridge/api/v1/router.py
"""Versioned API routes.

Health endpoints deliberately live at the app root (see api/main.py), not
here: a kubelet probe should not have to track the API version, and a
readiness check is a property of the process rather than of /api/v1.
"""

from typing import Any

from fastapi import APIRouter

from ill_bridge.api.v1.admin.router import router as admin_router
from ill_bridge.api.v1.libris.router import router as libris_router

api_router = APIRouter()

api_router.include_router(admin_router)
api_router.include_router(libris_router)


# Paths are relative to the prefix applied in create_app() ("/api/v1").
# Repeating the prefix here would produce /api/v1/api/v1/requests.
@api_router.get("/requests", tags=["requests"])
async def list_requests(tenant=None) -> dict[str, Any]:
    return {"items": [], "total": 0}
