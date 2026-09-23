from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx2
from typing_extensions import Self


class AsyncApiClient:
    """Reusable async JSON API client."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        headers: Mapping[str, str] | None = None,
        verify_ssl: bool = True,
        timeout: float | httpx2.Timeout = 10.0,
    ) -> None:
        default_headers = {"Accept": "application/json"}
        if api_key:
            default_headers["api-key"] = api_key

        self._base_url = base_url.rstrip("/") + "/"
        self._verify_ssl = verify_ssl
        self._timeout = httpx2.Timeout(timeout)
        self._headers = {**default_headers, **(headers or {})}
        self._session: httpx2.AsyncClient | None = None

    def _get_session(self) -> httpx2.AsyncClient:
        if self._session is None or self._session.is_closed:
            self._session = httpx2.AsyncClient(
                base_url=self._base_url,
                verify=self._verify_ssl,
                timeout=self._timeout,
                headers=self._headers,
            )
        return self._session

    @property
    def session(self) -> httpx2.AsyncClient:
        return self._get_session()

    @staticmethod
    def _path(uri: str) -> str:
        return uri.lstrip("/")

    @staticmethod
    def _body(response: httpx2.Response, uri: str) -> Any:
        if not response.content:
            return {"status": "deleted", "uri": uri}
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"response": response.text}

    async def get(
        self,
        uri: str,
        *,
        params: Mapping[str, str | int | float | bool | None] | None = None,
    ) -> Any:
        response = await self.session.get(self._path(uri), params=params)
        response.raise_for_status()
        return self._body(response, uri)

    async def post(self, uri: str, payload: Any) -> Any:
        response = await self.session.post(self._path(uri), json=payload)
        response.raise_for_status()
        return self._body(response, uri)

    async def put(self, uri: str, payload: Any) -> Any:
        response = await self.session.put(self._path(uri), json=payload)
        response.raise_for_status()
        return self._body(response, uri)

    async def delete(self, uri: str) -> Any:
        response = await self.session.delete(self._path(uri))
        response.raise_for_status()
        return self._body(response, uri)

    async def close(self) -> None:
        if self._session and not self._session.is_closed:
            await self._session.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()
