"""Keycloak Admin API client for provisioning OAuth clients.

Authentication follows :class:`~ill_bridge.common.folio_client.FolioApiClient`:
the bearer token is obtained from the Keycloak token endpoint with the
``client_credentials`` grant (service-account ``client_id`` + ``client_secret``)
and cached with a TTL -- never read from a pre-issued environment variable.
HTTP goes through httpx2.

All configuration (URL, realms, provisioner credentials, audience, timeout)
comes from :class:`~ill_bridge.config.Settings`.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx2
from ill_bridge.common.folio_client import AuthenticationError
from ill_bridge.config import Settings

logger = logging.getLogger(__name__)


class KeycloakAdminError(Exception):
    """Raised when a Keycloak Admin API operation fails."""


class KeycloakAdmin:
    """Keycloak Admin API client over httpx2.

    Mirrors ``FolioApiClient``: a single httpx2 session, a bearer token fetched
    from the Keycloak token endpoint with the ``client_credentials`` grant and
    cached with a TTL, and context-manager support so the pool is closed on
    exit. The token comes from ``client_id`` / ``client_secret`` -- never from a
    pre-issued env var.

    Everything is taken from :class:`~ill_bridge.config.Settings`:

    * ``keycloak_url``                 -- Keycloak base URL.
    * ``keycloak_realm``               -- realm being administered.
    * ``keycloak_admin_realm``         -- realm the provisioner authenticates to.
    * ``keycloak_admin_client_id``     -- provisioner service-account client id.
    * ``keycloak_admin_client_secret`` -- its secret.
    * ``keycloak_api_audience``        -- audience stamped on issued tokens.
    * ``keycloak_timeout`` / ``keycloak_verify_ssl`` -- transport options.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.keycloak_admin_client_id or (
            settings.keycloak_admin_client_secret is None
        ):
            raise KeycloakAdminError(
                "KEYCLOAK_ADMIN_CLIENT_ID and KEYCLOAK_ADMIN_CLIENT_SECRET must "
                "be configured to use the Keycloak Admin API"
            )

        self.base_url = settings.keycloak_url.rstrip("/")
        self.realm = settings.keycloak_realm  # realm being administered
        self.token_realm = settings.keycloak_admin_realm  # realm the token is from
        self.login_method = settings.keycloak_admin_login_method
        self.client_id = settings.keycloak_admin_client_id
        self.client_secret = settings.keycloak_admin_client_secret.get_secret_value()
        self.api_audience = settings.keycloak_api_audience
        self.admin_base = f"{self.base_url}/admin/realms/{self.realm}"

        self._http = httpx2.Client(
            timeout=httpx2.Timeout(settings.keycloak_timeout),
            verify=settings.keycloak_verify_ssl,
            headers={"Accept": "application/json"},
        )
        self._access_token: str | None = None
        self._token_obtained_at = 0.0
        self._token_ttl = 250.0

    def __enter__(self) -> "KeycloakAdmin":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------
    # Authentication (client_credentials, cached) -- cf. FolioApiClient
    # ------------------------------------------------------------------

    def inspect_token(self, access_token: str) -> None:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)

        claims = json.loads(base64.urlsafe_b64decode(payload))

        print("Token issuer:", claims.get("iss"))
        print("Token audience:", claims.get("aud"))
        print("Token client:", claims.get("azp"))
        print("Realm roles:", claims.get("realm_access", {}).get("roles", []))
        print(
            "Resource roles:",
            json.dumps(
                claims.get("resource_access", {}),
                indent=2,
            ),
        )

    def _get_access_token(self) -> str:
        """Return a cached access token, refreshing it when necessary."""
        """
        For login method user, you need to create a dedicated user `ill-bridge-provisioner` in the admin realm and
        use its username and password to obtain a token. 
        The user must have the necessary permissions to manage clients in the target realm
        and client scopes  `kc-admin-api`
        """

        if (
            self._access_token is not None
            and time.monotonic() - self._token_obtained_at < self._token_ttl
        ):
            self.inspect_token(self._access_token)
            return self._access_token

        token_url = (
            f"{self.base_url}/realms/{self.token_realm}/protocol/openid-connect/token"
        )
        if self.login_method == "cli":
            token_data = {
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": self.client_id,
                "password": self.client_secret,
            }
        else:
            token_data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        try:
            response = self._http.post(
                token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            payload = response.json()
            access_token = payload["access_token"]
            if not isinstance(access_token, str):
                raise TypeError
        except httpx2.HTTPStatusError as exc:
            # Keycloak explains the refusal in the body (e.g. invalid_client,
            # unauthorized_client). Surface it -- the status alone is useless.
            raise AuthenticationError(
                f"Failed to obtain access token for client_id={self.client_id!r} "
                f"from {token_url} (HTTP {exc.response.status_code}): "
                f"{exc.response.text}"
            ) from exc
        except httpx2.HTTPError as exc:
            raise AuthenticationError(
                f"Could not reach token endpoint {token_url}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise AuthenticationError(
                "Authentication response has no access token"
            ) from exc

        self._token_obtained_at = time.monotonic()
        self._token_ttl = max(float(payload.get("expires_in", 300)) - 50, 0)
        self._access_token = access_token
        self.inspect_token(self._access_token)
        return access_token

    def _headers(self) -> dict[str, str]:
        # No Content-Type here on purpose: httpx derives it from the body
        # (json= -> application/json, files= -> multipart/form-data with a
        # boundary, data= -> x-www-form-urlencoded). Forcing application/json
        # broke the multipart certificate upload ("keystoreFormat cannot be
        # null").
        return {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        allow_status: tuple[int, ...] = (),
        **kwargs: Any,
    ) -> httpx2.Response:
        """Call the Keycloak Admin API, raising on a non-2xx response.

        ``path`` is relative to the realm admin base, e.g. ``"clients"``.
        Status codes in ``allow_status`` (e.g. ``409``) are returned instead
        of raising, so callers can make an operation idempotent.
        """
        url = f"{self.admin_base}/{path.lstrip('/')}"
        response = self._http.request(method, url, headers=self._headers(), **kwargs)
        if not response.is_success and response.status_code not in allow_status:
            raise KeycloakAdminError(
                f"{method} {path} failed ({response.status_code}): {response.text}"
            )
        return response
    
    def test_login(self) -> None:
        """Test that the admin client can log in and obtain a token."""
        token = self._get_access_token()
        print("Obtained access token:", token)

    def create_university(
        self,
        *,
        client_id: str,
        tenant_id: str,
        certificate_path: str,
    ) -> str:
        certificate = Path(certificate_path).read_text()

        # 1. Create the university's OAuth client (idempotent: 409 = exists).
        created = self._request(
            "POST",
            "clients",
            allow_status=(409,),
            json={
                "clientId": client_id,
                "name": client_id,
                "description": f"ILL integration for {client_id}",
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": False,
                "clientAuthenticatorType": "client-jwt",
                "serviceAccountsEnabled": True,
                "standardFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "implicitFlowEnabled": False,
                "fullScopeAllowed": False,
                "attributes": {
                    "use.jwks.url": "false",
                },
            },
        )
        if created.status_code == 409:
            logger.info("Keycloak client %s already exists; reusing it", client_id)
        else:
            logger.info("Created Keycloak client %s", client_id)

        # 2. Resolve the internal Keycloak client UUID.
        response = self._request(
            "GET",
            "clients",
            params={"clientId": client_id},
        )
        clients = response.json()
        if not clients:
            raise KeycloakAdminError(f"Keycloak client {client_id} not found")

        client_uuid = clients[0]["id"]
        client_path = f"clients/{client_uuid}"

        # 3. Register the university's public certificate. This endpoint takes
        # multipart/form-data (a "keystoreFormat" field + a "file" part), not
        # JSON. "Certificate PEM" imports an X.509 cert and extracts its public
        # key for client-jwt (private_key_jwt) signature verification.
        self._request(
            "POST",
            f"{client_path}/certificates/jwt.credential/upload-certificate",
            data={"keystoreFormat": "Certificate PEM"},
            files={
                "file": (
                    Path(certificate_path).name,
                    certificate.encode("utf-8"),
                    "application/x-pem-file",
                )
            },
        )
        logger.info("Registered certificate for client %s", client_id)

        # 4. Add tenant_id as a hardcoded access-token claim (409 = exists).
        self._request(
            "POST",
            f"{client_path}/protocol-mappers/models",
            allow_status=(409,),
            json={
                "name": "tenant-id",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-hardcoded-claim-mapper",
                "config": {
                    "claim.name": "tenant_id",
                    "claim.value": tenant_id,
                    "jsonType.label": "String",
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                    "userinfo.token.claim": "false",
                },
            },
        )
        logger.info("Mapped tenant_id=%s onto client %s", tenant_id, client_id)

        # 5. Add the API audience to access tokens (409 = exists).
        self._request(
            "POST",
            f"{client_path}/protocol-mappers/models",
            allow_status=(409,),
            json={
                "name": "ill-bridge-api-audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "config": {
                    "included.client.audience": self.api_audience,
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                },
            },
        )
        logger.info("Added audience %s to client %s", self.api_audience, client_id)

        return client_uuid

    def create_api_audience_client(
        self,
        *,
        client_id: str | None = None,
    ) -> str:
        """Create the API audience client (e.g. ``ill-bridge-api``).

        Configured as:
        - Client type: OpenID Connect (protocol="openid-connect")
        - Client authentication: ON (publicClient=False)
        - Standard flow: OFF (standardFlowEnabled=False)
        - Direct access grants: OFF (directAccessGrantsEnabled=False)
        - Service accounts: OFF (serviceAccountsEnabled=False)
        - Root URL / Home URL: empty
        """
        target_client_id = client_id or self.api_audience

        created = self._request(
            "POST",
            "clients",
            allow_status=(409,),
            json={
                "clientId": target_client_id,
                "name": target_client_id,
                "description": "ILL Bridge API token audience",
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": False,
                "standardFlowEnabled": False,
                "directAccessGrantsEnabled": False,
                "serviceAccountsEnabled": False,
                "implicitFlowEnabled": False,
                "rootUrl": "",
                "baseUrl": "",
            },
        )
        if created.status_code == 409:
            logger.info(
                "Keycloak API audience client %s already exists; reusing it",
                target_client_id,
            )
        else:
            logger.info("Created Keycloak API audience client %s", target_client_id)

        response = self._request(
            "GET",
            "clients",
            params={"clientId": target_client_id},
        )
        clients = response.json()
        if not clients:
            raise KeycloakAdminError(f"Keycloak client {target_client_id} not found")

        return clients[0]["id"]


__all__ = [
    "AuthenticationError",
    "KeycloakAdmin",
    "KeycloakAdminError",
]
