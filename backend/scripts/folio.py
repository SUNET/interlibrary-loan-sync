"""
Usage:
    python patron_groups.py MDU BTH HH
    dotenvx run -f /home/benedith/github/library_project/.env -- uv run scripts/patron_groups.py MDU BTH HH

    uv run python scripts/folio.py get tenant --prefix BTH --code BTH-INST
    uv run python scripts/folio.py get library --prefix BTH --code Bthg
    uv run python scripts/folio.py tosql --prefix BTH --lib-code Bthg --uuid-from-folio
    uv run python scripts/folio.py tosql --prefix BTH --lib-code Bthg --save-to-file
    uv run python scripts/folio.py patron-groups MDU BTH HH
    dotenvx run -f /home/benedith/github/library_project/.env -- uv run python scripts/folio.py patron-groups MDU BTH HH

    ❯ dotenvx run -f /home/benedith/github/library_project/.env -- uv run python scripts/folio.py tosql --prefix HH --lib-code hhbib --uuid-from-folio --save-to-file
    ❯ dotenvx run -f /home/benedith/github/library_project/.env -- uv run python scripts/folio.py tosql --prefix MDU --lib-code BMDE --uuid-from-folio --save-to-file
    ❯ dotenvx run -f /home/benedith/github/library_project/.env -- uv run python scripts/folio.py tosql --prefix BTH --lib-code Bthg --uuid-from-folio --save-to-file


Environment variables for each prefix:
    TENANT_ENVIRONMENT_<PREFIX>
    TENANT_<PREFIX>
    FOLIO_USERNAME_<PREFIX>
    FOLIO_SECRET_<PREFIX>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ill_bridge.common.folio_client import FolioApiClient


DEFAULT_PREFIXES = ("MDU", "BTH", "HH")


USAGE_EXAMPLES = """Examples:
  uv run python scripts/folio.py get tenant --prefix BTH --code BTH-INST
  uv run python scripts/folio.py get library --prefix BTH --code Bthg
  uv run python scripts/folio.py tosql --prefix BTH --lib-code Bthg --uuid-from-folio
  uv run python scripts/folio.py tosql --prefix BTH --lib-code Bthg --save-to-file
  uv run python scripts/folio.py patron-groups MDU BTH HH

  python patron_groups.py MDU BTH HH
  dotenvx run -f /home/benedith/github/library_project/.env -- uv run scripts/patron_groups.py MDU BTH HH
  dotenvx run -f /home/benedith/github/library_project/.env -- uv run python scripts/folio.py patron-groups MDU BTH HH
"""


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
    account_key = f"{folio_tenant_key.lower()}-libris-1"

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
        true,
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
                f"env://{folio_tenant_key.upper()}_LIBRIS_PASSWORD",
            ),
            provider_sql(
                fake_provider_id,
                "fake",
                f"Fake-Libris ({tenant_name})",
                "http://localhost:9000/librisfjarrlan/api",
                f"env://{folio_tenant_key.upper()}_LIBRIS_PASSWORD",
            ),
        )
    )


def create_client_for_prefix(prefix: str) -> FolioApiClient:
    normalized_prefix = prefix.upper()
    tenant_env = os.getenv(f"TENANT_ENVIRONMENT_{normalized_prefix}", "test")
    tenant = os.getenv(f"TENANT_{normalized_prefix}", "diku")
    username = os.getenv(f"FOLIO_USERNAME_{normalized_prefix}")
    secret = os.getenv(f"FOLIO_SECRET_{normalized_prefix}")

    if not username:
        raise RuntimeError(f"Missing FOLIO_USERNAME_{normalized_prefix}")
    if not secret:
        raise RuntimeError(f"Missing FOLIO_SECRET_{normalized_prefix}")

    return FolioApiClient(
        username=username,
        secret=secret,
        auth_base_url=(
            f"https://auth.{normalized_prefix.lower()}-{tenant_env}.bibliotek.sunet.se"
        ),
        api_base_url=(
            f"https://api.{normalized_prefix.lower()}-{tenant_env}.bibliotek.sunet.se"
        ),
        realm=tenant,
        tenant=tenant,
    )


async def get_patron_groups(client: FolioApiClient) -> list[dict[str, Any]]:
    response = await client.get(
        "groups",
        params={"query": "cql.allRecords=1", "limit": 1000},
    )
    response.raise_for_status()
    return response.json().get("usergroups", [])


async def print_patron_groups_for_prefixes(prefixes: Sequence[str]) -> None:
    """Print FOLIO patron groups for each tenant prefix."""
    for prefix in prefixes:
        normalized_prefix = prefix.upper()
        print(f"\n{normalized_prefix} patron groups:")

        try:
            async with create_client_for_prefix(normalized_prefix) as client:
                patron_groups = await get_patron_groups(client)
        except Exception as exc:
            print(f"  Failed to retrieve patron groups: {exc}")
            continue

        if not patron_groups:
            print("  No patron groups found")
            continue

        for patron_group in patron_groups:
            print(json.dumps(patron_group, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query FOLIO data and helper resources.",
        epilog=USAGE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    get_parser = commands.add_parser("get", help="Get a FOLIO location unit")
    resources = get_parser.add_subparsers(dest="resource", required=True)

    tenant_parser = resources.add_parser("tenant", help="Get a tenant institution")
    tenant_parser.add_argument(
        "--prefix",
        required=True,
        help="Tenant prefix to connect to, for example BTH, MDU, or HH",
    )
    tenant_parser.add_argument("--code", help="FOLIO institution code")

    library_parser = resources.add_parser("library", help="Get a library")
    library_parser.add_argument(
        "--prefix",
        required=True,
        help="Tenant prefix to connect to, for example BTH, MDU, or HH",
    )
    library_parser.add_argument("--code", required=True, help="FOLIO library code")

    sql_parser = commands.add_parser("tosql", help="Generate tenant provider seed SQL")
    sql_parser.add_argument(
        "--prefix",
        required=True,
        help="Tenant prefix to connect to, for example BTH, MDU, or HH",
    )
    sql_parser.add_argument("--tenant-code", help="FOLIO institution code")
    sql_parser.add_argument(
        "--lib-code", required=True, help="FOLIO library code, for example Bthg"
    )
    sql_parser.add_argument(
        "--uuid-from-folio",
        action="store_true",
        help="use FOLIO UUIDs for the tenant and Libris provider",
    )
    sql_parser.add_argument(
        "--save-to-file",
        action="store_true",
        help="save generated SQL to <prefix>.sql instead of printing it",
    )

    patron_groups_parser = commands.add_parser(
        "patron-groups",
        help="Print FOLIO patron groups for tenant prefixes",
    )
    patron_groups_parser.add_argument(
        "prefixes",
        nargs="*",
        default=DEFAULT_PREFIXES,
        help="Tenant prefixes to check, for example MDU BTH HH",
    )
    return parser


async def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "patron-groups":
        await print_patron_groups_for_prefixes(args.prefixes)
        return 0

    async with create_client_for_prefix(args.prefix) as client:
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
            sql = create_seed_sql(
                tenant,
                library,
                args.prefix.lower(),
                args.uuid_from_folio,
            )
            if args.save_to_file:
                output_path = Path(f"{args.prefix.lower()}.sql")
                output_path.write_text(sql + "\n", encoding="utf-8")
                print(f"Saved SQL to {output_path}")
            else:
                print(sql)
            return 0

        if result is None:
            parser.error(f"{label.lower()} not found")
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    return asyncio.run(run(parser.parse_args(argv), parser))


if __name__ == "__main__":
    raise SystemExit(main())
