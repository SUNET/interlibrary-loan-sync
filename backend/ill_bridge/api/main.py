import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import random
from typing import Annotated
from fastapi import FastAPI, BackgroundTasks, Request, HTTPException, Depends, FastAPI, Response, status
from ill_bridge.jobs.tasks import ping, send_email
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from ill_bridge.api.v1.router import api_router
from ill_bridge.config import Settings, get_settings
from ill_bridge.jobs.app import app as procrastinate_app

logger = logging.getLogger(__name__)

# Annotated form of the dependency. Preferred over `Settings = Depends(...)`
# in the signature: it is reusable, keeps the default slot free, and avoids
# a function call in an argument default (ruff B008).
# TODO: Fix  it as done in network-watcher-project
SettingsDep = Annotated[Settings, Depends(get_settings)]


from faker import Faker
fake = Faker("sv_SE")
seq = 42
Faker.seed(seq)
rng = random.Random(seq)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle - startup and shutdown.
    Shutdown order matters: stop producers before closing what they use.
    """
    settings = get_settings()
    logger.info(
        "starting",
        extra={
            "environment": settings.environment,
            "sigel": settings.libris_sigel,
            "writes_enabled": settings.libris_writes_enabled,
        },
    )

    # Startup: create long-lived resources here, in dependency order.
    #   app.state.db = await create_engine(settings.database_url)
    #   app.state.libris = build_client(settings)
    #   app.state.poller = asyncio.create_task(poll_loop(app.state.libris))

    try:
        # Opens (and later closes) the async connection pool Procrastinate uses
        # to defer jobs. This is cheap -- deferring a job is just an INSERT.
        async with procrastinate_app.open_async():
            yield
    finally:
        # Shutdown: stop the background task first, then close clients.
        #   app.state.poller.cancel()
        #   with suppress(asyncio.CancelledError):
        #       await app.state.poller
        #   await app.state.libris.aclose()
        #   await app.state.db.dispose()
        logger.info("shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        root_path=settings.api_root_path,
        title=settings.api_title,
        version=settings.api_version,
        lifespan=lifespan,
    )

    # CORS middleware — added only when cross-origin access is configured.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Exception handlers
    # setup_exception_handlers(app)

    # Include API routes
    app.include_router(api_router, prefix="/api/v1")

    _register_health_routes(app)

    @app.post("/ping", tags=["test"])
    async def send_ping():

        task = await ping.defer_async()

        return {
            "status": "queued",
            "task_id": task,
        }
        
    @app.post("/webhooks/{source}")
    async def receive_webhook(source: str, request: Request):
        """Generic webhook receiver that immediately enqueues processing."""
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(400, "Invalid JSON")

        # Optionally verify signature here (Stripe, GitHub, etc.)

        await send_email.defer_async(
            to=fake.email(),
            subject=f"Webhook received from {source}",
            body=f"Payload: {payload}",
        )
        # Return 202 quickly – real work happens in the worker
        return {"status": "accepted"}, 202

    return app


def _register_health_routes(app: FastAPI) -> None:
    """Probe endpoints, mounted at the root rather than under /api/v1."""

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        """Liveness: is the process running?"""
        return {"status": "ok???"}

    @app.get("/health/ready", tags=["health"])
    async def ready(
        response: Response,
        settings: SettingsDep,
    ) -> dict[str, object]:
        """Readiness: can this instance accept durable work?

        Checks only what the service owns. A Libris outage is a *degraded*
        condition, never unreadiness: marking the pod unready removes it from
        the load balancer and stops staff reaching the dashboard and DLQ -
        exactly what they need during a provider outage.
        """
        checks: dict[str, str] = {}

        if settings.database_url:
            # Fails closed deliberately. Reporting "ok" without connecting
            # would let a pod with an unreachable database take traffic.
            checks["database"] = "unverified: check not implemented"
        if settings.redis_url:
            checks["redis"] = "unverified: check not implemented"

        ok = all(value == "ok" for value in checks.values())
        if not ok:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

        return {
            "status": "ok" if ok else "unready",
            "environment": settings.environment,
            "checks": checks,
        }


if __name__ == "__main__":
    # Development entry point: python -m ill_bridge.api.main
    #     uvicorn --factory ill_bridge.api.main:create_app
    import uvicorn

    try:
        _settings = get_settings()
        uvicorn.run(
            # Import string + factory=True so --reload can re-import the module.
            "ill_bridge.api.main:create_app",
            factory=True,
            host=_settings.api_host,
            port=_settings.api_port,
            reload=_settings.environment == "local",
        )
        logger.info(
            f"API running at http://{_settings.api_host}:{_settings.api_port}/api/v1 for environment {_settings.environment!r}"
        )
    except ValidationError as exc:
        print(exc.json(indent=2))
    except Exception as exc:
        logger.exception("Failed to load settings")
        raise SystemExit(1) from exc
