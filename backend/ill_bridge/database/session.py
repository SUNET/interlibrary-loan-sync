"""Async SQLAlchemy engine + session plumbing.

Procrastinate owns the same database (schema ``public``) so we can query
the ``procrastinate_*`` tables directly for read-only admin views.
Operational commands go through Procrastinate's JobManager -- never raw
UPDATE against ``procrastinate_jobs``.

Design notes
------------
* No module-level engine. Import time must not open connections; tests
  and scripts must be able to import repositories without a live DSN.
* :func:`make_engine` / :func:`make_sessionmaker` are the factories used
  both by the FastAPI lifespan (see ``ill_bridge.api.main``) and by
  standalone scripts (workers, ad-hoc jobs) that have no ``app.state``.
* :func:`get_db` is the FastAPI dependency. It resolves the sessionmaker
  off ``request.app.state`` -- so ``app.dependency_overrides`` works in
  tests without monkeypatching module globals.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ill_bridge.config import Settings


def async_dsn(dsn: str) -> str:
    """Coerce a plain ``postgresql://`` DSN to the asyncpg driver form.

    Procrastinate takes the plain form (psycopg); SQLAlchemy async needs
    ``postgresql+asyncpg://``. Same URL string in settings, both
    consumers happy.
    """
    if dsn.startswith("postgresql+"):
        return dsn
    if dsn.startswith("postgresql://"):
        return "postgresql+asyncpg://" + dsn[len("postgresql://") :]
    if dsn.startswith("postgres://"):
        return "postgresql+asyncpg://" + dsn[len("postgres://") :]
    return dsn


def make_engine(settings: Settings) -> AsyncEngine:
    if not settings.database_url:
        raise RuntimeError(
            "database_url is not configured; admin endpoints require it."
        )
    return create_async_engine(
        async_dsn(settings.database_url),
        pool_pre_ping=True,
    )


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def ping_db(engine: AsyncEngine, timeout_seconds: float = 5.0) -> None:
    """
    Round-trip ``SELECT 1`` through the engine's async pool.
    """
    async with asyncio.timeout(timeout_seconds):
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a session bound to app-lifespan state.

    Raises :class:`RuntimeError` if the lifespan did not set
    ``sessionmaker`` -- that is a wiring bug, not a request-time error.
    """
    sessionmaker: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "sessionmaker", None
    )
    if sessionmaker is None:
        raise RuntimeError(
            "app.state.sessionmaker is not set; lifespan did not initialise "
            "the database engine."
        )
    async with sessionmaker() as session:
        yield session
