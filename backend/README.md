# ILL Bridge — backend

Provider-agnostic interlibrary loan (*fjärrlån*) integration service between
FOLIO and Libris.

## Quick start

```bash
uv sync

export ILL_LIBRIS_API_KEY=<key>     # or HALMSTAD_LIBRIS_PASSWORD
export ILL_LIBRIS_SIGEL=Hal         # or HALMSTAD_LIBRIS_USERNAME
```

```bash
uvicorn --factory ill_bridge.api.main:create_app     # not main:app
uv run python -m ill_bridge.api.main        # dev, :8000 with reload
secretspec run -- uv run python -m ill_bridge.api.main
uvicorn ill_bridge.providers.fake.server_faker:app --port 9001 # faker ill api
```

```bash
uv run pytest                               # 16 tests
```

Production uses the **factory**, not a module-level app:

```bash
uvicorn --factory ill_bridge.api.main:create_app
```

`ill_bridge.api.main` deliberately has no module-level `app`. Instantiating at import time would make the module unimportable without valid config and break test collection.

## Layout

```
ill_bridge/
├── api/            FastAPI app factory, v1 router, health probes
├── domain/         canonical models, state machine, guards
├── application/    intake, provisioning, lending, cancellation
├── providers/      ILLProviderInterface, Libris adapter, fake provider
├── folio/          auth, inventory, circulation, users
├── persistence/    models, repositories, migrations
├── jobs/           scheduler, dispatcher, tasks
├── observability/  redaction, metrics, tracing
└── config.py       settings, validated once at startup
scripts/            Part 1 discovery tooling (see below)
tests/              unit, contracts, integration, live, fixtures
```

`application/` must never import a task-queue library, and `providers/` must
never import `folio/`. Those two rules keep the domain portable.

## Configuration

Environment variables, prefix `ILL_`. Precedence: kwargs → `os.environ` →
`.env` → defaults.

| Variable | Default | Notes |
| --- | --- | --- |
| `ILL_LIBRIS_API_KEY` | — | **Required.** Alias: `HALMSTAD_LIBRIS_PASSWORD` |
| `ILL_LIBRIS_SIGEL` | — | **Required.** Alias: `HALMSTAD_LIBRIS_USERNAME` |
| `ILL_LIBRIS_ALLOWED_SIGELS` | `[sigel]` | JSON list. The org-scoped key does not isolate tenants — this does |
| `ILL_LIBRIS_BASE_URL` | Libris production | Point at the fake provider for local work |
| `ILL_LIBRIS_WRITES_ENABLED` | `false` | Libris has no undo |
| `ILL_ENVIRONMENT` | `local` | `local` \| `test` \| `staging` \| `production` |
| `ILL_DATABASE_URL` / `ILL_REDIS_URL` | — | Required in staging/production |
| `ILL_CORS_ORIGINS` | `[]` | `"*"` is rejected at startup |

Auth is the **`api-key` header** only — Libris has no basic auth and no OAuth.

Guards that fail at boot rather than at runtime: mock auth outside `local`, unrecognised environment names, missing database/redis in staging or production, a sigel outside the allowlist, wildcard CORS origins.

## Health endpoints

| Endpoint | Behaviour |
| --- | --- |
| `/health/live` | Always 200 if the process runs. **No dependency checks** — a 503 tells the kubelet to restart, which cannot fix a database outage |
| `/health/ready` | 200 when it can accept durable work. **Fails closed**: 503 while a configured dependency has no implemented check |

A provider outage is *degraded*, never unready — marking the pod unready would cut staff off from the dashboard and DLQ exactly when they need them.

## Discovery scripts

```bash
uv run scripts/connectivity_check.py            # read-only probe; blocks writes
uv run scripts/collect_endpoints_response.py    # capture → tests/fixtures/libris/_raw/
uv run scripts/sanitize_fixtures.py             # redact PII → tests/fixtures/libris/
uv run scripts/discover_fields.py               # derive sanitiser constants
uv run scripts/field_coverage.py                # coverage + code/label matrix
```

## Tests

```bash
uv run pytest                    # unit + api
uv run pytest tests/live --live  # hits the real Libris sandbox; opt-in only
uvx ruff check ill_bridge/
```

`tests/live/` is a separate directory, not just a marker, so destructive tests cannot run unattended.

An autouse fixture in `conftest.py` strips `ILL_*` and `HALMSTAD_*` from the environment and clears the settings cache — without it, a developer with real credentials exported gets different results from CI.

interlibrary_loan
