"""Provision a university's Keycloak client for ILL Bridge.

Creates the OAuth client a university (one FOLIO tenant) uses to authenticate
to the ILL Bridge API with the private_key_jwt flow, registers its public
certificate, and stamps the issued access token with the tenant id and the API
audience.

The Keycloak Admin client lives in
:class:`ill_bridge.common.keycloak_admin.KeycloakAdmin` and is built from
:class:`ill_bridge.config.Settings`. This script only resolves settings and
provides a command-line entrypoint. The admin token is obtained from the
Keycloak token endpoint with the ``client_credentials`` grant -- never read
from the environment directly.
secretspec run -- uv run python -m scripts.keycloak.provision_university
Usage:
    from provision_university import provision_university

    client_uuid = provision_university(
        client_id="folio-hh",
        tenant_id="4d04e6d1-27d1-439e-8aa6-8992dbd7c623",
        certificate_path="folio-hh-credentials/public-cert.pem",
    )

Configuration (ill_bridge.config.Settings; bare KEYCLOAK_* names also accepted):
    KEYCLOAK_URL                  Keycloak base URL (default http://localhost:8081)
    KEYCLOAK_REALM                Realm being administered (default "ill-bridge")
    KEYCLOAK_ADMIN_REALM          Realm the provisioner authenticates against
                                  (default "master")
    KEYCLOAK_ADMIN_CLIENT_ID      Provisioner service-account client id
    KEYCLOAK_ADMIN_CLIENT_SECRET  Provisioner service-account client secret
    KEYCLOAK_API_AUDIENCE         Audience stamped on tokens (default ill-bridge-api)
"""

import logging
import time
from pathlib import Path
from uuid import uuid4
import json

import httpx2
import jwt
from dotenv import load_dotenv
from ill_bridge.common.keycloak_admin import KeycloakAdmin
from ill_bridge.config import Settings, get_settings

logger = logging.getLogger(__name__)

JWT_BEARER_ASSERTION = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def create_api_audience_client(
    *,
    client_id: str | None = None,
    settings: Settings | None = None,
) -> str:
    """Create the ``ill-bridge-api`` audience client in Keycloak.

    Configures an OpenID Connect confidential client with standard flow,
    direct access grants, and service accounts disabled, and empty Root/Home URLs.
    """
    settings = settings or get_settings(strict_env=False)
    with KeycloakAdmin(settings) as admin:
        return admin.create_api_audience_client(client_id=client_id)


def test_keycloak_login() -> None:
    settings =  get_settings(strict_env=False)
    with KeycloakAdmin(settings) as admin:
        return admin.test_login()

def provision_university(
    *,
    client_id: str,
    tenant_id: str,
    certificate_path: str,
    settings: Settings | None = None,
) -> str:
    settings = settings or get_settings(strict_env=False)
    print("Provisioning Keycloak client for university:", settings)
    # print(settings.keycloak_admin_client_secret)
    with KeycloakAdmin(settings) as admin:
        return admin.create_university(
            client_id=client_id,
            tenant_id=tenant_id,
            certificate_path=certificate_path,
        )


def get_client_access_token(
    *,
    client_id: str,
    private_key_path: str,
    settings: Settings | None = None,
) -> str:
    """Obtain an access token for a provisioned university client.

    Counterpart to :func:`provision_university`: the university authenticates
    with the **private_key_jwt** flow -- a short-lived JWT ``client_assertion``
    signed with its private key, matching the ``client-jwt`` authenticator the
    provisioning configured against its uploaded public certificate.

    The token is issued by the realm the client lives in
    (``settings.keycloak_realm``, e.g. ``ill-bridge``), not the admin realm.
    """
    settings = settings or get_settings(strict_env=False)
    token_url = (
        f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
        "/protocol/openid-connect/token"
    )

    private_key = Path(private_key_path).read_text()
    now = int(time.time())
    assertion = jwt.encode(
        {
            "iss": client_id,
            "sub": client_id,
            "aud": token_url,
            "iat": now,
            "exp": now + 60,
            "jti": str(uuid4()),
        },
        private_key,
        algorithm="RS256",
    )

    response = httpx2.post(
        token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_assertion_type": JWT_BEARER_ASSERTION,
            "client_assertion": assertion,
        },
        timeout=settings.keycloak_timeout,
        verify=settings.keycloak_verify_ssl,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def test_create_api_audience_client(client_id: str = "ill-bridge-api") -> None:
    """Smoke test for creating the ill-bridge-api audience client."""
    settings = get_settings(strict_env=False)
    client_uuid = create_api_audience_client(
        client_id=client_id,
        settings=settings,
    )
    print("Provisioned API audience client UUID:", client_uuid)


def test_provision_university(client_id="bth-ill-api-client") -> None:
    """Test the provision_university script end-to-end.

    This is a smoke test that provisions a Keycloak client for a university,
    then obtains an access token for it. It does not clean up the client.
    """
    settings = get_settings(strict_env=False)
    tenant_id = "4d04e6d1-27d1-439e-8aa6-8992dbd7c623"
    certificate_path = "/home/benedith/github/library_project/interlibrary_loan_system/secrets/bth/public-cert.pem"

    print("Provisioning Keycloak client for university:", settings)
    client_uuid = provision_university(
        client_id=client_id,
        tenant_id=tenant_id,
        certificate_path=certificate_path,
        settings=settings,
    )
    print("Provisioned Keycloak client UUID:", client_uuid)


def test_get_access_token(client_id="bth-ill-api-client") -> None:
    """Test obtaining an access token for a provisioned university client.

    This is a smoke test that uses an existing Keycloak client for a university
    to obtain an access token. It does not provision a new client.
    """
    settings = get_settings(strict_env=False)
    private_key_path = "/home/benedith/github/library_project/interlibrary_loan_system/secrets/bth/private.pem"

    access_token = get_client_access_token(
        client_id=client_id,
        private_key_path=private_key_path,
        settings=settings,
    )
    claims = jwt.decode(
        access_token,
        options={"verify_signature": False},
        algorithms=["RS256"],
    )

    print(json.dumps(claims.get("resource_access", {}), indent=2))
    print("Claims:", json.dumps(claims, indent=2))
    print("Obtained access token for university:", access_token)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    load_dotenv()
    print("Provisioning API audience client...")
    # test_keycloak_login()
    # test_create_api_audience_client(client_id="ill-bridge-api")
    # test_provision_university(client_id="bth-ill-api-client")
    test_get_access_token(client_id="bth-ill-api-client")
