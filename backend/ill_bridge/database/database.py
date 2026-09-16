"""Async SQLAlchemy engine bound to ``settings.database_url``.

Procrastinate owns the same database (schema ``public``) so we can query
``procrastinate_jobs`` / ``procrastinate_events`` / ``procrastinate_workers`` /
``procrastinate_periodic_defers`` directly for read-only admin views.

Operational commands (retry / cancel / enqueue) go through Procrastinate's
own JobManager -- never raw UPDATE against ``procrastinate_jobs``.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ill_bridge.config import get_settings


def _async_dsn(dsn: str) -> str:
    """Coerce a plain ``postgresql://`` DSN to the asyncpg driver form.

    Procrastinate needs the plain form (it uses psycopg); SQLAlchemy async
    needs ``postgresql+asyncpg://``. Same URL string in settings, both
    consumers happy.
    """
    if dsn.startswith("postgresql+"):
        return dsn
    if dsn.startswith("postgresql://"):
        return "postgresql+asyncpg://" + dsn[len("postgresql://") :]
    if dsn.startswith("postgres://"):
        return "postgresql+asyncpg://" + dsn[len("postgres://") :]
    return dsn


_settings = get_settings()
if not _settings.database_url:
    raise RuntimeError(
        "database_url is not configured; admin endpoints require it."
    )

engine = create_async_engine(
    _async_dsn(_settings.database_url),
    pool_pre_ping=True,
)

SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
