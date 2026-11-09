from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest

from testcontainers.community.postgres import PostgresContainer

from ill_bridge.config import get_settings


MANAGED_PREFIXES = ("ILL_", "HALMSTAD_", "MDE_", "MDV_")


# ---------------------------------------------------------------------------
# FOLIO test doubles
# ---------------------------------------------------------------------------
#
# ``find_patron`` only ever calls ``await client.get(...)``, then
# ``response.raise_for_status()`` and ``response.json()``. These stand-ins
# reproduce exactly that surface so patron lookups -- and the order intake
# that depends on them -- can be tested without a network or a real FOLIO.


class FakeFolioResponse:
    """Minimal stand-in for the httpx response ``find_patron`` consumes."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"FOLIO returned HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


class FakeFolioClient:
    """Canned ``FolioApiClient`` replacement with recorded calls.

    * ``users`` -- the list returned under ``{"users": [...]}``.
    * ``raise_on_get`` -- raise this instead of answering (transport error).
    * ``status_code`` -- HTTP status the fake response reports.
    * ``payload`` -- override the whole JSON body (e.g. a malformed shape).
    """

    def __init__(
        self,
        users: list[dict[str, Any]] | None = None,
        *,
        raise_on_get: BaseException | None = None,
        status_code: int = 200,
        payload: Any = None,
    ) -> None:
        self._users = users or []
        self._raise = raise_on_get
        self._status = status_code
        self._payload = payload
        self.calls: list[tuple[str, Any]] = []

    async def get(self, endpoint: str, params: Any = None, **_: Any) -> FakeFolioResponse:
        self.calls.append((endpoint, params))
        if self._raise is not None:
            raise self._raise
        payload = self._payload if self._payload is not None else {"users": self._users}
        return FakeFolioResponse(payload, self._status)


@pytest.fixture
def folio_client_factory():
    """Return a builder for :class:`FakeFolioClient` instances."""

    def _make(**kwargs: Any) -> FakeFolioClient:
        return FakeFolioClient(**kwargs)

    return _make


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Prevent tests from inheriting external configuration."""
    for name in list(os.environ):
        if name.startswith(MANAGED_PREFIXES):
            monkeypatch.delenv(name, raising=False)

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def minimal_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Minimum configuration required to instantiate Settings."""
    values = {
        "ILL_LIBRIS_API_KEY": "test-key",
        "ILL_LIBRIS_SIGEL": "Hal",
    }

    for key, value in values.items():
        monkeypatch.setenv(key, value)

    get_settings.cache_clear()
    return values


@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    """Start one PostgreSQL container for the test session."""
    with PostgresContainer("postgres:17") as container:
        yield container


@pytest.fixture
def database_env(
    minimal_env: dict[str, str],
    postgres: PostgresContainer,
    monkeypatch: pytest.MonkeyPatch,
):
    """Settings configured to use the disposable PostgreSQL instance."""
    database_url = postgres.get_connection_url()

    monkeypatch.setenv("ILL_DATABASE_URL", database_url)

    get_settings.cache_clear()

    yield get_settings()

    get_settings.cache_clear()


@pytest.fixture
def database_env_async_psycopg2(
    minimal_env: dict[str, str],
    postgres: PostgresContainer,
    monkeypatch: pytest.MonkeyPatch,
):
    """Settings configured to use the disposable PostgreSQL instance."""
    database_url = postgres.get_connection_url().replace(
        "postgresql+psycopg2://",
        "postgresql+asyncpg://",
    )

    monkeypatch.setenv("ILL_DATABASE_URL", database_url)
    get_settings.cache_clear()

    yield get_settings()

    get_settings.cache_clear()
    
@pytest.fixture
def database_env_async(
    minimal_env: dict[str, str],
    postgres: PostgresContainer,
    monkeypatch: pytest.MonkeyPatch,
):
    database_url = postgres.get_connection_url().replace(
        "postgresql+psycopg2://",
        "postgresql://",
        1,
    )

    monkeypatch.setenv("ILL_DATABASE_URL", database_url)
    get_settings.cache_clear()

    yield get_settings()

    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# ORM schema + seeded tenant for borrowing-order tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def orm_schema(postgres: PostgresContainer) -> bool:
    """Create every ORM-mapped table on the shared container, once.

    Built from ``Base.metadata`` rather than the raw SQL migrations: the
    models carry the same column types and CHECK constraints the tests care
    about, and ``create_all`` sidesteps the migrations' role/GRANT setup that
    assumes the production ``ill`` database. Row-level security is not
    reproduced -- the testcontainer superuser bypasses it anyway, and the
    repository filters every query by ``tenant_id`` explicitly.
    """
    from sqlalchemy import create_engine

    import ill_bridge.database.models  # noqa: F401  registers every table
    from ill_bridge.database.base import Base

    sync_url = postgres.get_connection_url().replace(
        "postgresql+psycopg2://", "postgresql+psycopg://", 1
    )
    engine = create_engine(sync_url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()
    return True


@pytest.fixture
def borrowing_env(orm_schema: bool, database_env_async) -> SimpleNamespace:
    """Schema-ready database plus one freshly seeded tenant.

    Returns a namespace with:

    * ``settings``        -- Settings pointed at the container.
    * ``async_url``       -- asyncpg DSN for building AsyncEngines in tests.
    * ``tenant_id``       -- the seeded tenant's id.
    * ``folio_tenant_key``-- its FOLIO key (unique per test to avoid clashes).

    Each test seeds its own tenant with fresh identifiers, so the shared
    session-scoped container needs no truncation between tests.
    """
    from sqlalchemy import insert
    from sqlalchemy.ext.asyncio import create_async_engine

    from ill_bridge.database.models import Tenants
    from ill_bridge.database.session import async_dsn

    settings = database_env_async
    async_url = async_dsn(settings.database_url)

    tenant_id = uuid.uuid4()
    folio_tenant_key = f"t{tenant_id.hex[:10]}"

    async def _seed() -> None:
        engine = create_async_engine(async_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    insert(Tenants).values(
                        id=tenant_id,
                        folio_tenant_key=folio_tenant_key,
                        name="Test Tenant",
                        infodisk_email="infodisk@example.org",
                    )
                )
        finally:
            await engine.dispose()

    asyncio.run(_seed())

    return SimpleNamespace(
        settings=settings,
        async_url=async_url,
        tenant_id=tenant_id,
        folio_tenant_key=folio_tenant_key,
    )