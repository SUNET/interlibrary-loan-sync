"""Smoke tests for the FastAPI application factory.

Several of these are regression guards for bugs found during review:

* readiness must fail closed when a dependency is configured but unchecked;
* routes must not carry a doubled /api/v1 prefix;
* probes must sit outside the versioned API;
* CORS must not mount with an empty origin list.

``create_app()`` is called per test rather than reusing the module-level
``app``, so each test observes its own configuration.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from ill_bridge import __version__
from ill_bridge.api.main import create_app


@pytest.fixture
def client(minimal_env: dict[str, str]) -> Iterator[TestClient]:
    """A client whose lifespan has run, so startup/shutdown are exercised."""
    with TestClient(create_app()) as test_client:
        yield test_client


class TestApplicationFactory:
    def test_builds_from_settings(self, minimal_env: dict[str, str]) -> None:
        app = create_app()
        assert app.title == "ILL Bridge"
        assert app.version == __version__

    def test_root_path_is_applied(
        self, monkeypatch: pytest.MonkeyPatch, minimal_env: dict[str, str]
    ) -> None:
        monkeypatch.setenv("ILL_API_ROOT_PATH", "/ill")
        assert create_app().root_path == "/ill"

    def test_lifespan_completes(self, minimal_env: dict[str, str]) -> None:
        """Regression guard: lifespan previously had no yield, so the app
        could not start at all."""
        with TestClient(create_app()) as client:
            assert client.get("/health/live").status_code == 200


class TestLiveness:
    def test_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_unaffected_by_configured_dependencies(
        self, monkeypatch: pytest.MonkeyPatch, minimal_env: dict[str, str]
    ) -> None:
        """Liveness must ignore dependencies entirely.

        A 503 here tells the kubelet to restart, which cannot fix a database
        outage and would crash-loop every replica simultaneously.
        """
        monkeypatch.setenv("ILL_DATABASE_URL", "postgresql://unreachable/db")
        monkeypatch.setenv("ILL_REDIS_URL", "redis://unreachable:6379/0")
        with TestClient(create_app()) as client:
            assert client.get("/health/live").status_code == 200


class TestReadiness:
    def test_ok_when_no_dependencies_configured(self, client: TestClient) -> None:
        response = client.get("/health/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["checks"] == {}

    @pytest.mark.parametrize(
        ("variable", "value", "expected_check"),
        [
            ("ILL_DATABASE_URL", "postgresql://x/db", "database"),
            ("ILL_REDIS_URL", "redis://x:6379/0", "redis"),
        ],
    )
    def test_fails_closed_for_unverified_dependency(
        self,
        monkeypatch: pytest.MonkeyPatch,
        minimal_env: dict[str, str],
        variable: str,
        value: str,
        expected_check: str,
    ) -> None:
        """Regression guard: reporting ready without connecting would let a
        pod with an unreachable dependency take traffic. Until a real check
        exists, readiness must report unready."""
        monkeypatch.setenv(variable, value)
        with TestClient(create_app()) as client:
            response = client.get("/health/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unready"
        assert expected_check in body["checks"]

    def test_reports_environment(self, client: TestClient) -> None:
        assert client.get("/health/ready").json()["environment"] == "local"


class TestRouting:
    def test_requests_endpoint_has_no_doubled_prefix(
        self, client: TestClient
    ) -> None:
        """Regression guard: the route was declared as "/api/v1/requests"
        inside a router already mounted at prefix="/api/v1"."""
        assert client.get("/api/v1/requests").status_code == 200
        assert client.get("/api/v1/api/v1/requests").status_code == 404

    def test_probes_are_outside_the_versioned_api(
        self, client: TestClient
    ) -> None:
        """A kubelet probe should not have to track the API version."""
        assert client.get("/health/live").status_code == 200
        assert client.get("/api/v1/health/live").status_code == 404

    def test_openapi_paths(self, minimal_env: dict[str, str]) -> None:
        paths = set(create_app().openapi()["paths"])
        assert paths == {"/api/v1/requests", "/health/live", "/health/ready"}


class TestCors:
    @staticmethod
    def _has_cors(app) -> bool:
        return any(m.cls is CORSMiddleware for m in app.user_middleware)

    def test_absent_when_no_origins_configured(
        self, minimal_env: dict[str, str]
    ) -> None:
        """A same-origin Stripes deployment needs no CORS middleware, and an
        empty origin list can never produce a successful preflight."""
        assert not self._has_cors(create_app())

    def test_present_when_origins_configured(
        self, monkeypatch: pytest.MonkeyPatch, minimal_env: dict[str, str]
    ) -> None:
        monkeypatch.setenv("ILL_CORS_ORIGINS", '["https://folio.example.org"]')
        assert self._has_cors(create_app())

    def test_wildcard_origin_rejected_at_startup(
        self, monkeypatch: pytest.MonkeyPatch, minimal_env: dict[str, str]
    ) -> None:
        """Browsers reject "*" alongside allow_credentials=True, so a wildcard
        yields a silently broken CORS setup rather than a permissive one."""
        monkeypatch.setenv("ILL_CORS_ORIGINS", '["*"]')
        with pytest.raises(ValueError, match=r'cannot contain "\*"'):
            create_app()
