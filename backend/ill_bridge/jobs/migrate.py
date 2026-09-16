import asyncio
import os
import subprocess
import sys

import procrastinate


async def schema_exists() -> bool:
    app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(
            conninfo=os.environ["ILL_DATABASE_URL"]
        )
    )

    async with app.open_async():
        # SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'procrastinate_jobs');
        result = await app.connector.execute_query_one_async(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_name = 'procrastinate_jobs'
            )
            """
        )
        print(f"Procrastinate schema exists: {result}")
        print(f"Procrastinate schema exists: {type(result)}")
        print(f"Procrastinate schema exists: {dir(result)}")
        
        return result['exists']  # type: ignore


def main() -> None:
    if asyncio.run(schema_exists()):
        print("Procrastinate schema already exists. Skipping. ++")
        sys.exit(0)


    print("Procrastinate schema does not exist. Creating...")
    subprocess.run(
        [
            "procrastinate",
            "--app=ill_bridge.jobs.app.app",
            "schema",
            "--apply",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
