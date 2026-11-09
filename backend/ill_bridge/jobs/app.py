from procrastinate import App, PsycopgConnector
from ill_bridge.config import Settings, get_settings

# settings = get_settings(
#     strict_env=False
# )  # fail fast on missing env vars, .env, or .toml

# app = App(
#     connector=PsycopgConnector(
#         # Procrastinate uses the same database as the domain tables — that is
#         # the point. Same transaction, same backup, same restore.
#         conninfo=settings.database_url,
#     ),
# )


def create_procrastinate_app(
    settings: Settings | None = None,
) -> App:
    settings = settings or get_settings(strict_env=False)

    app = App(
        connector=PsycopgConnector(
            # Procrastinate uses the same database as the domain tables — that is
            # the point. Same transaction, same backup, same restore.
            conninfo=settings.database_url,
        ),
    )
    return app
