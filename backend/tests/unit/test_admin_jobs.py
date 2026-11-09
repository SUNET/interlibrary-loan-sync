"""Admin job detail and lifecycle event API contracts."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql


@pytest.fixture
def client(minimal_env: dict[str, str]):
    from ill_bridge.api.main import create_app
    from ill_bridge.database.session import get_db
    from ill_bridge.dependencies.jobs import get_procrastinate_service
    from ill_bridge.services.procrastinate import ProcrastinateService

    app = create_app()

    async def fake_db():
        yield None

    # A repository-backed service with the repo mocked: the service's
    # composition/validation runs for real, only the SQL layer is faked.
    repo = MagicMock()
    service = ProcrastinateService(repo, MagicMock())

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_procrastinate_service] = lambda: service

    test_client = TestClient(app)
    test_client.repo = repo  # exposed so tests can stub SELECTs
    yield test_client


def test_job_detail_and_newest_events(client: TestClient) -> None:
    client.repo.get_job = AsyncMock(
        return_value={"id": 42, "task_name": "sample", "status": "failed"}
    )
    client.repo.get_job_events = AsyncMock(
        return_value=[{"id": 3, "job_id": 42, "type": "failed"}]
    )

    assert client.get("/api/v1/admin/jobs/42").json()["task_name"] == "sample"
    response = client.get("/api/v1/admin/jobs/42/events?limit=25")
    assert response.status_code == 200
    assert response.json() == [{"id": 3, "job_id": 42, "type": "failed"}]
    client.repo.get_job_events.assert_awaited_once_with(42, limit=25)


def test_events_for_missing_job_return_404(client: TestClient) -> None:
    client.repo.get_job = AsyncMock(return_value=None)
    get_events = AsyncMock()
    client.repo.get_job_events = get_events

    assert client.get("/api/v1/admin/jobs/42").status_code == 404
    assert client.get("/api/v1/admin/jobs/42/events").status_code == 404
    get_events.assert_not_awaited()


@pytest.mark.parametrize("limit", [0, 501])
def test_events_limit_is_bounded(client: TestClient, limit: int) -> None:
    assert client.get(f"/api/v1/admin/jobs/42/events?limit={limit}").status_code == 422


def test_event_history_queries_latest_first(minimal_env: dict[str, str]) -> None:
    import asyncio

    from ill_bridge.repositories.procrastinate import ProcrastinateRepository

    session = MagicMock()
    session.execute = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.mappings.return_value.all.return_value = []

    repo = ProcrastinateRepository(session)
    assert asyncio.run(repo.get_job_events(42, limit=25)) == []
    stmt = session.execute.call_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "procrastinate_events.job_id = 42" in sql
    assert "ORDER BY procrastinate_events.id DESC" in sql
    assert "LIMIT 25" in sql
