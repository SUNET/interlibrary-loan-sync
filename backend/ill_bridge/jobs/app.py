from procrastinate import App, PsycopgConnector
from ill_bridge.config import get_settings

settings = get_settings(strict_env=False)  # fail fast on missing env vars, .env, or .toml

app = App(
    connector=PsycopgConnector(
        # Procrastinate uses the same database as the domain tables — that is
        # the point. Same transaction, same backup, same restore.
        conninfo=settings.database_url,
    ),
)
