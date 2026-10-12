from __future__ import annotations

import os
import time
import uuid
from collections.abc import Mapping
from typing import Any

import httpx2
from ill_bridge.common.models import (
    ProviderRequestObservation,
    ReceivingLibrary,
)
from typing_extensions import Self


class FolioApiClient:
    """Async FOLIO API client with cached Keycloak authentication."""

    def __init__(
        self,
        username: str,
        secret: str,
        auth_base_url: str = "https://auth.sunet-test.bibliotek.sunet.se",
        api_base_url: str = "https://api.sunet-test.bibliotek.sunet.se",
        realm: str = "diku",
        tenant: str = "diku",
        timeout: float | httpx2.Timeout = 30.0,
        verify_ssl: bool = True,
    ) -> None:
        self.username = username
        self.secret = secret
        self.auth_base_url = auth_base_url.rstrip("/")
        self.api_base_url = api_base_url.rstrip("/") + "/"
        self.realm = realm
        self.tenant = tenant
        self._timeout = httpx2.Timeout(timeout)
        self._verify_ssl = verify_ssl
        self._session: httpx2.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_obtained_at = 0.0
        self._token_ttl = 250.0

    def _get_session(self) -> httpx2.AsyncClient:
        if self._session is None or self._session.is_closed:
            self._session = httpx2.AsyncClient(
                base_url=self.api_base_url,
                verify=self._verify_ssl,
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        return self._session

    @property
    def session(self) -> httpx2.AsyncClient:
        return self._get_session()

    async def _get_access_token(self) -> str:
        """Return a cached access token, refreshing it when necessary."""
        if (
            self._access_token is not None
            and time.monotonic() - self._token_obtained_at < self._token_ttl
        ):
            return self._access_token

        try:
            response = await self.session.post(
                f"{self.auth_base_url}/realms/{self.realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.username,
                    "client_secret": self.secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            payload = response.json()
            access_token = payload["access_token"]
            if not isinstance(access_token, str):
                raise TypeError
        except httpx2.HTTPError as exc:
            raise AuthenticationError("Failed to obtain access token") from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError(
                "Authentication response has no access token"
            ) from exc

        self._token_obtained_at = time.monotonic()
        self._token_ttl = max(float(payload.get("expires_in", 300)) - 50, 0)
        self._access_token = access_token
        return access_token

    async def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {await self._get_access_token()}",
            "Content-Type": content_type,
            "x-okapi-tenant": self.tenant,
        }

    @staticmethod
    def _path(endpoint: str) -> str:
        return endpoint.lstrip("/")

    async def get(
        self,
        endpoint: str,
        params: Mapping[str, str | int | float | bool | None] | None = None,
        **kwargs: Any,
    ) -> httpx2.Response:
        return await self.session.get(
            self._path(endpoint),
            headers=await self._headers(),
            params=params,
            **kwargs,
        )

    async def post(
        self,
        endpoint: str,
        json_data: Any = None,
        data: Any = None,
        **kwargs: Any,
    ) -> httpx2.Response:
        content_type = (
            "application/json"
            if json_data is not None
            else "application/x-www-form-urlencoded"
        )
        return await self.session.post(
            self._path(endpoint),
            headers=await self._headers(content_type),
            json=json_data,
            data=data,
            **kwargs,
        )

    async def put(
        self,
        endpoint: str,
        json_data: Any = None,
        data: Any = None,
        **kwargs: Any,
    ) -> httpx2.Response:
        return await self._write("PUT", endpoint, json_data, data, **kwargs)

    async def patch(
        self,
        endpoint: str,
        json_data: Any = None,
        data: Any = None,
        **kwargs: Any,
    ) -> httpx2.Response:
        return await self._write("PATCH", endpoint, json_data, data, **kwargs)

    async def _write(
        self,
        method: str,
        endpoint: str,
        json_data: Any,
        data: Any,
        **kwargs: Any,
    ) -> httpx2.Response:
        content_type = (
            "application/json"
            if json_data is not None
            else "application/x-www-form-urlencoded"
        )
        return await self.session.request(
            method,
            self._path(endpoint),
            headers=await self._headers(content_type),
            json=json_data,
            data=data,
            **kwargs,
        )

    async def delete(self, endpoint: str, **kwargs: Any) -> httpx2.Response:
        return await self.session.delete(
            self._path(endpoint), headers=await self._headers(), **kwargs
        )

    def invalidate_token(self) -> None:
        self._access_token = None
        self._token_obtained_at = 0.0

    @property
    async def access_token(self) -> str:
        return await self._get_access_token()

    async def close(self) -> None:
        if self._session and not self._session.is_closed:
            await self._session.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()


def get_folio_client() -> FolioApiClient:
    environment = os.getenv("ILL_ENVIRONMENT", "test")
    library_tenant = os.getenv("ILL_TENANT_NAME", "bth")
    folio_tenant = os.getenv("ILL_FOLIO_TENANT", "diku")
    return FolioApiClient(
        username=os.environ["ILL_FOLIO_TENANT_USERNAME"],
        secret=os.environ["ILL_FOLIO_TENANT_SECRET"],
        auth_base_url=(
            f"https://auth.{library_tenant.lower()}-{environment}.bibliotek.sunet.se"
        ),
        api_base_url=(
            f"https://api.{library_tenant.lower()}-{environment}.bibliotek.sunet.se"
        ),
        realm=folio_tenant,
        tenant=folio_tenant,
    )


async def api_get(
    client,
    endpoint: str,
    params: dict | None = None,
) -> list[dict]:
    """General GET request to retrieve all records from a FOLIO endpoint."""
    if params is None:
        params = {"limit": 1000, "offset": 0}
    response = await client.get(endpoint, params=params)
    response.raise_for_status()
    data = await response.json()
    return data


async def get_folio_patron_group(
    client: FolioApiClient, group_name: str
) -> dict | None:
    """Retrieve a FOLIO patron group by name."""
    response = await client.get(
        "groups",
        params={
            "query": f'group=="{group_name}"',
            "limit": 1000,
        },
    )
    response.raise_for_status()
    user_groups = (await response.json()).get("usergroups", [])
    patron_group = next(
        (group for group in user_groups if group.get("group") == group_name),
        None,
    )

    if patron_group is None:
        raise ValueError(f"FOLIO patron group '{group_name}' not found")

    return patron_group


async def create_folio_requesting_library(
    client: FolioApiClient,
    receiving_library: ReceivingLibrary,
    patron_group_id: str,
) -> dict:
    """Create a FOLIO requesting library unless it already exists."""
    username = receiving_library.library_code
    existing_response = await client.get(
        "users",
        params={"query": f'username=="{username}"', "limit": 1},
    )
    existing_response.raise_for_status()
    existing_users = existing_response.json().get("users", [])
    if existing_users:
        response =  {
            "id": existing_users[0].get("id"),
            "status_code": existing_response.status_code,
            "text": existing_response.text,
            "url": existing_response.url,
            "is_success": existing_response.is_success,
            "is_error": existing_response.is_error,
            "created": False,
        }
        print(
            f"Requesting library '{username}' already exists in FOLIO. Skipping creation."
        )
        return response

    payload = {
        "active": True,
        "personal": {
            "preferredContactTypeId": "002",
            "lastName": receiving_library.name or "",
            "email": receiving_library.email or "",
        },
        "username": receiving_library.library_code,
        "type": "",
        "preferredEmailCommunication": [],
        "patronGroup": patron_group_id,
        "id": str(uuid.uuid4()),
        "departments": [],
    }
    response = await client.post("users", json_data=payload)
    response.raise_for_status()
    return {
        "id": payload["id"],
        "status_code": response.status_code,
        "text": response.text,
        "url": response.url,
        "is_success": response.is_success,
        "is_error": response.is_error,
        "created": True,
    }


class AuthenticationError(Exception):
    """Raised when FOLIO authentication fails."""
