import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from fastapi import FastAPI, Request, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ill_bridge.api.v1.router import api_router
from ill_bridge.config import Settings, get_settings
from ill_bridge.database.session import make_engine, make_sessionmaker, ping_db
from ill_bridge.jobs.worker import app as procrastinate_app

logger = logging.getLogger(__name__)

# Annotated form of the dependency. Preferred over `Settings = Depends(...)`
# in the signature: it is reusable, keeps the default slot free, and avoids
# a function call in an argument default (ruff B008).
SettingsDep = Annotated[Settings, Depends(get_settings)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle - startup and shutdown.
    Shutdown order matters: stop producers before closing what they use.
    """
    settings = get_settings(strict_env=False)  # fail fast on missing env vars, .env, or .toml
    logger.info(
        "starting",
        extra={
            "environment": settings.environment,
            "sigel": settings.libris_sigel,
            "writes_enabled": settings.libris_writes_enabled,
        },
    )

    # Startup: create long-lived resources here, in dependency order.
    # SQLAlchemy engine is bound to the app, not to a module import, so
    # tests can import routers without a live DSN and so the connection
    # pool is closed on shutdown (matters under SIGTERM in containers).
    engine = make_engine(settings)
    try:
        # Explicit fail-fast on Postgres. Same driver as the request path
        # so this can't disagree with /health/ready. If we skip this,
        # procrastinate_app.open_async() below will also blow up, but with
        # a less obvious error message.
        await ping_db(engine)
    except Exception as exc:
        # Loud + explicit: operators must see WHY startup failed. No DSN
        # in the message (would leak credentials); host is safe.
        logger.error(
            "startup aborted: database is unreachable "
            "(check ILL_DATABASE_URL and Postgres status): %s: %s",
            exc.__class__.__name__,
            exc,
        )
        await engine.dispose()  # do not leak the pool on failed startup
        raise RuntimeError(
            "Database unreachable at startup; see log above."
        ) from exc

    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)

    try:
        # Opens (and later closes) the async connection pool Procrastinate uses
        # to defer jobs. This is cheap -- deferring a job is just an INSERT.
        async with procrastinate_app.open_async():
            yield
    finally:
        # Shutdown: producers first (none yet), then close clients.
        #   app.state.poller.cancel()
        #   with suppress(asyncio.CancelledError):
        #       await app.state.poller
        #   await app.state.libris.aclose()
        await engine.dispose()
        logger.info("shutdown complete")


def _register_health_routes(app: FastAPI) -> None:
    """Probe endpoints, mounted at the root rather than under /api/v1."""

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        """Liveness: is the process running?"""
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready(
        request: Request,
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

        # Database: SELECT 1 through the same pool the request path uses.
        # A short timeout keeps a hung Postgres from turning readiness into
        # a slow-lorris on the kubelet.
        engine = getattr(request.app.state, "engine", None)
        if engine is None:
            checks["database"] = "unwired: lifespan did not set app.state.engine"
        else:
            try:
                await ping_db(engine, timeout_seconds=2.0)
                checks["database"] = "ok"
            except (SQLAlchemyError, TimeoutError, OSError) as exc:
                # Log the exception class + message; never the DSN.
                logger.warning(
                    "readiness: database check failed: %s",
                    exc.__class__.__name__,
                )
                checks["database"] = f"error: {exc.__class__.__name__}"

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


def create_app() -> FastAPI:
    # TODO: Convert to true in production: uvicorn --factory ill_bridge.api.main:create_app
    #   will then fail fast on missing env vars, .env, or .toml
    settings = get_settings(strict_env=False) 

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

    app.include_router(api_router, prefix="/api/v1")
    _register_health_routes(app)

    return app


if __name__ == "__main__":
    # Development entry point: python -m ill_bridge.api.main
    #     uvicorn --factory ill_bridge.api.main:create_app
    import uvicorn

    try:
        _settings = get_settings(strict_env=False)  # fail fast on missing env vars, .env, or .toml
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
