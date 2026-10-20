"""Typed async client for the ill-bridge Admin REST API.

One :class:`AdminApiClient` instance per UI process, created at NiceGUI startup
and closed at shutdown. Pages call the typed methods; the client centralises
timeout, base URL, and error handling.

All read methods return plain ``dict``/``list`` so the caller can bind them
directly to Quasar tables without an extra Pydantic layer. If drift with the
backend response schema becomes a maintenance burden, add a shared schemas
package — do not import backend Pydantic models here (deploy coupling).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx2

logger = logging.getLogger(__name__)


class AdminApiError(RuntimeError):
    """Raised for non-2xx responses or transport failures.

    Callers should catch this at the page boundary and surface it via
    :func:`ui.notify` while continuing to render last-known data.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AdminApiClient:
    """Thin async wrapper over the ``/admin/*`` REST endpoints."""

    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        # AsyncClient keeps a connection pool; one instance per process is
        # correct. Do not create per-request.
        self._client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------- internals ---------------------------------------------------

    async def _get(self, path: str, **params: Any) -> Any:
        # Drop keys with None so query strings stay clean.
        params = {k: v for k, v in params.items() if v is not None}
        try:
            r = await self._client.get(path, params=params)
        except httpx2.HTTPError as exc:
            logger.warning("admin api GET %s failed: %s", path, exc)
            raise AdminApiError(f"GET {path} failed: {exc}") from exc
        if r.status_code >= 400:
            raise AdminApiError(
                f"GET {path} -> {r.status_code}: {r.text[:200]}",
                status_code=r.status_code,
            )
        return r.json()

    async def _post(self, path: str, *, json: dict[str, Any] | None = None) -> Any:
        try:
            r = await self._client.post(path, json=json or {})
        except httpx2.HTTPError as exc:
            logger.warning("admin api POST %s failed: %s", path, exc)
            raise AdminApiError(f"POST {path} failed: {exc}") from exc
        if r.status_code >= 400:
            raise AdminApiError(
                f"POST {path} -> {r.status_code}: {r.text[:200]}",
                status_code=r.status_code,
            )
        return r.json()

    # ---------- jobs (reads) ------------------------------------------------

    async def list_jobs(
        self,
        *,
        status: str | None = None,
        queue: str | None = None,
        task_name: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self._get(
            "/admin/jobs",
            status=status, queue=queue, task_name=task_name, limit=limit,
        )

    async def list_failed_jobs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return await self._get("/admin/jobs/failed", limit=limit)

    async def list_running_jobs(self) -> list[dict[str, Any]]:
        return await self._get("/admin/jobs/running")

    async def get_job(self, job_id: int) -> dict[str, Any]:
        return await self._get(f"/admin/jobs/{job_id}")

    async def get_job_events(self, job_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self._get(f"/admin/jobs/{job_id}/events", limit=limit)

    # ---------- jobs (operations) ------------------------------------------

    async def cancel_job(self, job_id: int, *, abort: bool = False) -> dict[str, Any]:
        return await self._post(f"/admin/jobs/{job_id}/cancel", json={"abort": abort})

    async def retry_job(
        self,
        job_id: int,
        *,
        queue: str | None = None,
        priority: int | None = None,
        lock: str | None = None,
    ) -> dict[str, Any]:
        body = {k: v for k, v in (
            ("queue", queue), ("priority", priority), ("lock", lock),
        ) if v is not None}
        return await self._post(f"/admin/jobs/{job_id}/retry", json=body)

    async def run_task(
        self, task_name: str, *, kwargs: dict[str, Any] | None = None, queue: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"kwargs": kwargs or {}}
        if queue is not None:
            body["queue"] = queue
        return await self._post(f"/admin/jobs/{task_name}/run", json=body)

    # ---------- queues / workers / scheduler --------------------------------

    async def list_queues(self) -> dict[str, list[dict[str, Any]]]:
        """Return ``{"depth": [...], "oldest_waiting": [...]}``.

        - ``depth`` rows: ``{queue_name, status, count}`` — one row per
          (queue, status) pair. Status is Procrastinate's raw string
          (``todo``/``doing``/``failed``/``succeeded``/``cancelled``/``aborted``).
        - ``oldest_waiting`` rows: ``{queue_name, oldest_seconds}`` — only
          queues that currently have ``todo`` jobs are represented.
        """
        return await self._get("/admin/queues")

    async def queue_jobs(self, queue: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return await self._get(f"/admin/queues/{queue}/jobs", limit=limit)

    async def list_workers(self) -> list[dict[str, Any]]:
        return await self._get("/admin/workers")

    async def scheduler(self) -> dict[str, Any]:
        return await self._get("/admin/scheduler")
