import secrets
from collections.abc import Callable
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
)
from ill_bridge.common.models import ApiClientIdentity
from ill_bridge.config import Settings, get_settings
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from pwdlib import PasswordHash

settings: Settings = get_settings(strict_env=False)


ISSUER = f"{settings.keycloak_url.rstrip('/')}/realms/{settings.keycloak_realm}"
AUDIENCE = settings.keycloak_api_audience
JWKS_URL = f"{ISSUER}/protocol/openid-connect/certs"

jwks_client = PyJWKClient(JWKS_URL)
password_hash = PasswordHash.recommended()

bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="ILL Bridge university client access token",
    auto_error=True,
)

admin_basic = HTTPBasic(
    scheme_name="AdminBasicAuth",
    description="ILL Bridge administrator username and password",
)

def require_admin(
    credentials: Annotated[
        HTTPBasicCredentials,
        Depends(admin_basic),
    ],
) -> str:
    settings = get_settings(strict_env=False)
    if (
        settings.api_admin_username is None
        or settings.api_admin_password_hashed is None
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Administrator authentication is not configured",
        )

    username_valid = secrets.compare_digest(
        credentials.username,
        settings.api_admin_username,
    )

    password_valid = password_hash.verify(
        credentials.password,
        settings.api_admin_password_hashed.get_secret_value(),
    )

    if not (username_valid and password_valid):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrator credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


def get_current_client(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> ApiClientIdentity:
    token = credentials.credentials

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=ISSUER,
            audience=AUDIENCE,
            options={
                "require": ["exp", "iat", "iss", "aud", "sub", "azp", "tenant_id"],
            },
        )

        roles = frozenset(
            claims.get("resource_access", {}).get("ill-bridge-api", {}).get("roles", [])
        )

        return ApiClientIdentity(
            client_id=claims["azp"],
            tenant_id=UUID(claims["tenant_id"]),
            roles=roles,
        )

    except (InvalidTokenError, PyJWKClientError, KeyError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_roles(*required_roles: str) -> Callable:

    async def check_roles(
        identity: ApiClientIdentity = Depends(get_current_client),
    ) -> ApiClientIdentity:

        missing = set(required_roles) - identity.roles

        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": "Insufficient permissions",
                    "required_roles": sorted(required_roles),
                    "missing_roles": sorted(missing),
                },
            )

        return identity

    return check_roles
