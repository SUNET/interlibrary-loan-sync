# ILL Bridge — UI

Two NiceGUI portals sharing one Python package.

- **admin** — internal ops dashboard (jobs, workers, queues, scheduler).
  Entry point: `python -m ill_bridge_ui.admin.main` or `ill-admin-ui`.
- **librisportal** — librarian-facing UI (stub for now).
  Entry point: `python -m ill_bridge_ui.librisportal.main` or `ill-libris-ui`.

Each portal runs in its own process/container. They import shared code from
`ill_bridge_ui.shared.{clients,components,i18n,layout}`.

## Architecture

The UI talks to the backend **only** through the versioned REST API
(`/api/v1/admin/*`). No direct DB access. See `ill_bridge_ui/shared/clients/admin.py`
for the typed httpx2 client.

Rationale: single source of truth for validation/auth, deployable independently,
same contract usable by future consumers (librisportal, CLI, dashboards).

## Environment

All settings use the `ILL_UI_` prefix (via `pydantic-settings`):

| Var                       | Default                            | Purpose                 |
|---------------------------|------------------------------------|-------------------------|
| `ILL_UI_ADMIN_API_BASE`   | `http://backend:8000/api/v1`       | Backend REST base URL   |
| `ILL_UI_HOST`             | `0.0.0.0`                          | Bind host               |
| `ILL_UI_PORT`             | `8080`                             | Bind port               |
| `ILL_UI_DEFAULT_LANG`     | `sv`                               | Fallback language       |
| `ILL_UI_ENVIRONMENT`      | `local`                            | Header pill label       |

## Folder layout

```
ill_bridge_ui/
  admin/            portal 1: entry + routes + pages + nav config + assets/
  librisportal/     portal 2: stub (own assets/ later)
  shared/           clients, components, i18n, layout — importable by both
```

## Development

```bash
uv sync
ILL_UI_ADMIN_API_BASE=http://localhost:8000/api/v1 uv run ill-admin-ui
```

Open <http://localhost:8080>.

In the admin portal, select a job ID from Jobs or the overview to inspect its
status, arguments and the latest 100 Procrastinate lifecycle events. The events
are not task output or exception logs: per-job execution logs are not currently
stored by the backend.

## Notes

- `storage_secret` in each `main.py` is currently a placeholder. Replace with
  a real secret (env var) before shipping — it signs the per-user cookie that
  holds the language choice.
- Adding a view = add one `NavItem` to `admin/nav_config.py` + one page module
  + one entry in `admin/routes.py`.
- Adding a language = add a top-level dict in `shared/i18n/strings.py` and
  the code in `SUPPORTED_LANGS`.
