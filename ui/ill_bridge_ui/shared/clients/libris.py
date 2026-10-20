"""Typed async client for the Libris ILL API (``iller.libris.kb.se``).

One :class:`LibrisApiClient` per UI process, created at NiceGUI startup and
closed at shutdown. The librisportal talks to Libris **directly** for reads;
only writes and enrichment go through the ill-bridge backend.

Behaviours of the upstream API that this client deliberately preserves:

* Authentication is an ``api-key`` **header** — not a bearer token, not basic
  auth. Every request carries it.
* Every path is scoped to our sigel (``library_code``). An unknown sigel
  returns ``count: 0``, **never a 404** — so a misconfigured sigel is
  indistinguishable from a quiet week. :meth:`view` therefore returns the
  envelope's ``count`` alongside the records so pages can surface the
  difference rather than silently rendering an empty table.
* There is no pagination and no request-creation endpoint. Views return the
  full set; filtering is our job, client-side.
* ``last_modified`` is an opaque epoch string used for optimistic concurrency.
  Store and resend it **verbatim** — never parse and reserialise it.

Direction follows the *payload*, not the endpoint name: ``/incoming`` and
``/recent`` are LENDING views (another library is asking us), while ``/inbox``
and ``/may_reserve`` are BORROWING views (we are asking someone else).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx2

logger = logging.getLogger(__name__)

# Views where the payload describes us lending out (utlån).
LENDING_VIEWS = ("incoming", "recent", "reservations", "cancellations")
# Views where the payload describes us borrowing in (inlån).
BORROWING_VIEWS = ("inbox", "may_reserve", "notfullfilled", "delivered", "last")


class LibrisApiError(RuntimeError):
    """Raised for non-2xx responses or transport failures.

    Callers should catch this at the page boundary and surface it via
    :func:`ui.notify` while continuing to render last-known data.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LibrisApiClient:
    """Thin async wrapper over the Libris ILL REST API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        sigel: str,
        *,
        timeout: float = 10.0,
        generate: int = 0,
    ) -> None:
        self.sigel = sigel
        # Simulator-only knob; the real API rejects `generate`. Kept on the
        # client so pages never have to know which provider they are talking to.
        self._generate = generate
        # AsyncClient keeps a connection pool; one instance per process is
        # correct. Do not create per-request.
        self._client = httpx2.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers={"api-key": api_key},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---------- internals ---------------------------------------------------

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        params = {k: v for k, v in params.items() if v is not None}
        try:
            r = await self._client.get(path, params=params)
        except httpx2.HTTPError as exc:
            logger.warning("libris api GET %s failed: %s", path, exc)
            raise LibrisApiError(f"GET {path} failed: {exc}") from exc
        if r.status_code >= 400:
            raise LibrisApiError(
                f"GET {path} -> {r.status_code}: {r.text[:200]}",
                status_code=r.status_code,
            )
        return r.json()

    # ---------- ILL request views ------------------------------------------

    async def view(
        self, view: str, *, media_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return the ``ill_requests`` records for a named view.

        ``media_type`` is the only filter the upstream API supports and takes
        ``"loan"`` or ``"copy"``.
        """
        payload = await self._get(
            f"/illrequests/{self.sigel}/{view}",
            media_type=media_type,
            generate=self._generate or None,
        )
        return payload.get("ill_requests", [])

    async def get_request(self, request_id: str) -> dict[str, Any] | None:
        """Fetch a single record by ``request_id`` or ``lf_number``.

        Returns ``None`` when the record is not visible to our sigel — the API
        answers with an empty envelope rather than a 404.
        """
        payload = await self._get(f"/illrequests/{self.sigel}/{request_id}")
        records = payload.get("ill_requests", [])
        return records[0] if records else None

    # ---------- library directory ------------------------------------------

    async def libraries(self, target: str = "all_libraries") -> list[dict[str, Any]]:
        """Library directory. ``target`` may be a sigel, a comma-separated list
        of sigels, or ``all_libraries`` (~5 200 records in production)."""
        payload = await self._get(
            f"/libraries/{self.sigel}/{target}",
            generate=self._generate or None,
        )
        return payload.get("libraries", [])

    async def our_library(self) -> dict[str, Any] | None:
        """The directory entry for our own sigel, or ``None`` if unavailable."""
        records = await self.libraries(self.sigel)
        return records[0] if records else None
