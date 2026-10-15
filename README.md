# ILL Bridge — *gemensam fjärrlånelösning*

A provider-agnostic interlibrary loan service bridging **FOLIO** and **Libris**, built for a Swedish university library consortium.

It ingests ILL transactions from Libris, verifies patrons against FOLIO, provisions temporary inventory for incoming loans, tracks outgoing loans against local holdings, and synchronises state in both directions, as far as the Libris contract actually permits.

## Layout

| Path | Contents |
| --- | --- |
| `backend/` | Python service — FastAPI, domain model, provider adapters, workers |
| `frontend/` | FOLIO Stripes staff module (React/TypeScript) |
| `e2e/` | Playwright tests spanning UI → API → FOLIO |
| `deploy/` | Docker Compose and Helm |

Start with [`backend/README.md`](backend/README.md).

```bash
Usage
# Docker
docker compose -f docker-compose-dev.yml up migrate
# Locally (as before, or both steps via the same script)
secretspec run -- uv run pyway migrate
secretspec run -- uv run python -m ill_bridge.jobs.migrate
```

## Two directions

**Inlån (borrowing):** a local patron needs material held elsewhere. The request arrives from Libris, the patron is verified against `mod-users`, a temporary item and circulation request are created, and FOLIO's own notice policy tells the patron when it arrives.

**Utlån (lending):** another library needs material we hold. Staff select an existing item, check it out to an institutional borrower account, and record shipment.

## Three principles

**Provider messages are observations, not commands.** A Libris status of *Levererad* does not mean the book is on the hold shelf — only a FOLIO check-in proves that, and the Libris documentation notes not every library sets it.

**Uncertainty is displayed, never guessed.** Unknown statuses, ambiguous patron matches and uncertain write outcomes become reviewable work. Readiness checks fail closed rather than claim health they have not verified.

**Capabilities are gated by evidence.** Adapters declare what they support, and the domain refuses to invent an action the provider lacks.
