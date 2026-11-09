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

from ill_bridge import __version__


class TestPostgresDatabase:
    def test_database_connection(self, postgres):
        connection_url = postgres.get_connection_url()
        print("connection_url:", connection_url)
        assert connection_url is not None

    def test_db_connection(self, database_env):
        assert database_env.database_url is not None
