from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from collections.abc import Sequence
from typing import Any

from ill_bridge.common.folio_client import FolioApiClient


async def get_tenant(
    client: FolioApiClient, code: str | None = None
) -> dict[str, Any] | None:
    """Return the institution matching code, or the first institution."""
    params = {"query": f'code=="{code}"'} if code else None
    response = await client.get("location-units/institutions", params=params)
    response.raise_for_status()
    institutions = response.json().get("locinsts", [])
    if code is None:
        return next(iter(institutions), None)
    return next(
        (institution for institution in institutions if institution.get("code") == code),
        None,
    )


async def get_library(client: FolioApiClient, code: str) -> dict[str, Any] | None:
    """Return the library matching code."""
    response = await client.get(
        "location-units/libraries",
        params={"query": f'code=="{code}"'},
    )
    response.raise_for_status()
    return next(
        (
            library
            for library in response.json().get("loclibs", [])
            if library.get("code") == code
        ),
        None,
    )


def sql_string(value: str) -> str:
    """Quote a string as a PostgreSQL literal."""
    return "'" + value.replace("'", "''") + "'"


def create_seed_sql(
    tenant: dict[str, Any],
    library: dict[str, Any],
    folio_tenant_key: str,
    uuid_from_folio: bool = False,
) -> str:
    """Create tenant and provider seed SQL from FOLIO location units."""
    if uuid_from_folio:
        tenant_id = str(uuid.UUID(str(tenant["id"])))
        libris_provider_id = str(uuid.UUID(str(library["id"])))
    else:
        tenant_id = str(uuid.uuid4())
        libris_provider_id = str(uuid.uuid4())
    fake_provider_id = str(uuid.uuid4())
    tenant_name = str(tenant["name"])
    library_code = str(library["code"])
    account_key = f"{folio_tenant_key.lower()}-main"

    tenant_values = ",\n        ".join(
        map(sql_string, (tenant_id, folio_tenant_key, tenant_name))
    )

    def provider_sql(
        provider_id: str,
        adapter_key: str,
        display_name: str,
        base_url: str,
        secret_ref: str,
    ) -> str:
        values = (
            provider_id,
            tenant_id,
            adapter_key,
            account_key,
            display_name,
            library_code,
            base_url,
            secret_ref,
        )
        quoted_values = ",\n        ".join(map(sql_string, values))
        return f"""INSERT INTO providers (
    id,
    tenant_id,
    adapter_key,
    account_key,
    display_name,
    local_library_code,
    base_url,
    secret_ref,
    enabled,
    writes_enabled,
    mapping_version
)
VALUES (
        {quoted_values},
        true,
        false,
        {sql_string(f"{adapter_key}-v1")}
);"""

    return "\n\n".join(
        (
            f"""INSERT INTO tenants (id, folio_tenant_key, name)
VALUES (
        {tenant_values}
);""",
            provider_sql(
                libris_provider_id,
                "libris",
                f"Libris ({tenant_name})",
                "https://iller.libris.kb.se/librisfjarrlan/api",
                "env://ILL_LIBRIS_API_KEY",
            ),
            provider_sql(
                fake_provider_id,
                "fake",
                f"Fake-Libris ({tenant_name})",
                "http://localhost:9000/librisfjarrlan/api",
                "env://ILL_FAKE_API_KEY",
            ),
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query FOLIO location units.")
    commands = parser.add_subparsers(dest="command", required=True)

    get_parser = commands.add_parser("get", help="Get a FOLIO location unit")
    resources = get_parser.add_subparsers(dest="resource", required=True)

    tenant_parser = resources.add_parser("tenant", help="Get a tenant institution")
    tenant_parser.add_argument("--code", help="FOLIO institution code")

    library_parser = resources.add_parser("library", help="Get a library")
    library_parser.add_argument("--code", required=True, help="FOLIO library code")

    sql_parser = commands.add_parser("tosql", help="Generate tenant provider seed SQL")
    sql_parser.add_argument("--tenant-code", help="FOLIO institution code")
    sql_parser.add_argument(
        "--lib-code", required=True, help="FOLIO library code, for example Bthg"
    )
    sql_parser.add_argument(
        "--uuid-from-folio",
        action="store_true",
        help="use FOLIO UUIDs for the tenant and Libris provider",
    )
    return parser


def create_client() -> FolioApiClient:
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


async def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    async with create_client() as client:
        if args.command == "get" and args.resource == "tenant":
            result = await get_tenant(client, args.code)
            label = "Institution"
        elif args.command == "get" and args.resource == "library":
            result = await get_library(client, args.code)
            label = "Library"
        else:
            tenant = await get_tenant(client, args.tenant_code)
            if tenant is None:
                parser.error(f"tenant not found: {args.tenant_code or '<first>'}")
            library = await get_library(client, args.lib_code)
            if library is None:
                parser.error(f"library not found: {args.lib_code}")
            print(
                create_seed_sql(
                    tenant,
                    library,
                    os.getenv("ILL_TENANT_NAME", "bth").lower(),
                    args.uuid_from_folio,
                )
            )
            return 0

        if result is None:
            parser.error(f"{label.lower()} not found")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    return asyncio.run(run(parser.parse_args(argv), parser))


if __name__ == "__main__":
    """_summary_
        Commands:
        uv run python scripts/folio.py get tenant [--code BTH-INST]
        uv run python scripts/folio.py get library --code Bthg
        uv run python scripts/folio.py tosql [--tenant-code BTH-INST] --lib-code Bthg
        # Use FOLIO UUIDs
        uv run python scripts/folio.py tosql --lib-code Bthg --uuid-from-folio
    """
    raise SystemExit(main())
