"""Bring the database schema up to date.

Run order (both in the same database):
  1. Domain schema  — versioned SQL in ``migrations/`` applied by pyway.
  2. Queue schema   — Procrastinate's tables, applied once if missing.

Used by the ``migrate`` service in deploy/docker-compose-dev.yml, and locally:

    secretspec run -- uv run python -m ill_bridge.jobs.migrate

pyway reads its connection settings from the PYWAY_* environment variables.
"""

import asyncio
import os
import subprocess
import sys

import procrastinate


def run_pyway() -> None:
    """Apply pending domain migrations. pyway skips already-applied versions
    and fails on checksum mismatch, so this is safe to run on every start."""
    print("Applying domain migrations with pyway...", flush=True)
    subprocess.run(["pyway", "info"], check=False)
    subprocess.run(["pyway", "migrate"], check=True)


async def procrastinate_schema_exists() -> bool:
    app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(
            conninfo=os.environ["ILL_DATABASE_URL"]
        )
    )
    async with app.open_async():
        result = await app.connector.execute_query_one_async(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'procrastinate_jobs'
            )
            """
        )
        return bool(result["exists"])  # type: ignore[index]


def run_procrastinate() -> None:
    if asyncio.run(procrastinate_schema_exists()):
        print("Procrastinate schema already exists. Skipping.", flush=True)
        return

    print("Procrastinate schema does not exist. Creating...", flush=True)
    subprocess.run(
        ["procrastinate", "--app=ill_bridge.jobs.app.app", "schema", "--apply"],
        check=True,
    )


def main() -> None:
    try:
        run_pyway()
        run_procrastinate()
    except subprocess.CalledProcessError as exc:
        print(f"Migration failed: {exc}", file=sys.stderr, flush=True)
        sys.exit(exc.returncode or 1)
    print("Migrations complete.", flush=True)


if __name__ == "__main__":
    main()
