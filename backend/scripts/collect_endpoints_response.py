"""Capture raw Libris ILL API responses into the fixture corpus.

Roadmap Part 1c — fixture corpus expansion.

Writes to ``tests/fixtures/libris/_raw/`` (gitignored — the payloads contain
live patron data). Sanitise with ``sanitize_fixtures.py`` before committing.

Safety
------
The transport rejects every non-read HTTP method before it reaches the
network. Libris writes are irreversible — there is no undo — so this guard
is not a formality.

Behaviour
---------
A failing endpoint does not abort the run: this is a discovery script, so it
collects what it can and reports the rest. The closing summary is the actual
deliverable — it shows which views returned records and, per Part 1b, whether
the patron field is ever populated.

Usage
-----
    HALMSTAD_LIBRIS_USERNAME=Hal \\
    HALMSTAD_LIBRIS_PASSWORD=<api-key> \\
    uv run scripts/collect_endpoints_response.py

Optional:
    --sigel Hal         override the sigel
    --months 12         archive window to walk back (default 12)
    --chunk-days 30     archive slice size (default 30)
    --include-inbox     opt in to /inbox (see warning below)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterator

import httpx2

BASE = os.environ.get(
    "LIBRIS_BASE", "https://iller.libris.kb.se/librisfjarrlan/api"
)

# NOTE: the secretspec names are misleading. USERNAME holds the *sigel*
# (e.g. "Hal") and PASSWORD holds the *api-key*. Libris has no basic auth;
# authentication is the "api-key" header only. Kept aligned with
# secretspec.toml rather than renamed here.
ENV_SIGEL = "HALMSTAD_LIBRIS_USERNAME"
ENV_API_KEY = "HALMSTAD_LIBRIS_PASSWORD"

# Anchored to the script location, NOT the current working directory, so the
# corpus lands in the same place regardless of where the script is invoked.
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "tests" / "fixtures" / "libris" / "_raw"

READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}

# Direction is relative to the sigel in the path.
#   incoming  = another library asks us   -> we lend    (utlån)
#   outgoing  = we ask another library    -> we borrow  (inlån)
LENDING_VIEWS = ("incoming", "recent", "reservations", "cancellations")
BORROWING_VIEWS = ("may_reserve", "notfullfilled", "delivered", "last")

# Reading /inbox does NOT clear it; xstatus is only reset by POST action=read,
# which is a write we have not certified yet (roadmap Part 11). Polling it
# read-only lets a librarian's real inbox grow unbounded, so it is opt-in.
INBOX_VIEW = "inbox"


class ReadOnlyTransport(httpx2.HTTPTransport):
    """Refuse any method that could mutate Libris state."""

    def handle_request(self, request):
        if request.method not in READ_ONLY_METHODS:
            raise RuntimeError(
                f"BLOCKED {request.method} {request.url} — capture is read-only"
            )
        return super().handle_request(request)


class Capture:
    """Fetch, persist and tally one endpoint at a time."""

    def __init__(self, client: httpx2.Client) -> None:
        self.client = client
        self.results: list[dict[str, Any]] = []

    def fetch(self, url: str, name: str) -> dict[str, Any] | None:
        out = RAW_DIR / f"{name}.json"
        row: dict[str, Any] = {"name": name, "count": None, "note": ""}

        try:
            response = self.client.get(url)
        except Exception as exc:  # noqa: BLE001 — report, never abort the run
            row["note"] = f"request failed: {type(exc).__name__}: {exc}"
            self.results.append(row)
            print(f"  ✗ {name:<28} {row['note']}")
            return None

        if response.status_code != 200:
            # Status codes are undocumented for every endpoint; record what we see.
            row["note"] = f"HTTP {response.status_code}"
            self.results.append(row)
            print(f"  ✗ {name:<28} HTTP {response.status_code}")
            return None
       
        data = response.json()
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

 
        # out.write_text(response.text, encoding="utf-8")

        try:
            body = response.json()
        except ValueError:
            row["note"] = "non-JSON body (saved anyway)"
            self.results.append(row)
            print(f"  ? {name:<28} non-JSON body, {len(response.content)} bytes")
            return None

        records = _records(body)
        row["count"] = len(records)
        row["with_patron"] = sum(1 for r in records if str(r.get("user", "")).strip())
        row["media_types"] = sorted(_codes(records, "media_type_code"))
        row["status_codes"] = sorted(_codes(records, "status_code"))
        self.results.append(row)

        print(f"  ✓ {name:<28} count={row['count']}")
        return body


def _records(body: Any) -> list[dict[str, Any]]:
    """Pull the record array out of the Libris envelope.

    Envelope shape: {data_source, data_type, result_type, library_code,
    count, <array>}. There is no cursor, offset or next link anywhere.
    """
    if not isinstance(body, dict):
        return []
    for key in ("ill_requests", "user_requests", "libraries"):
        value = body.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def _codes(records: list[dict[str, Any]], field: str) -> set[str]:
    """Collect the distinct non-empty values of a ``*_code`` field.

    Codes arrive as strings ("1", "2"), never integers. Mapping is done on
    these, never on the Swedish label.
    """
    out: set[str] = set()
    for record in records:
        value = record.get(field)
        if value not in (None, ""):
            out.add(str(value))
    return out


def harvest_enduser_ids() -> set[str]:
    """Collect enduser_id values from ILL responses already written to disk.

    Only Websearch-originated requests carry one; the rest hold the "0"
    sentinel. These are the keys for /userrequests?user_id=, which is a
    different namespace from ill_requests[].user_id.
    """
    found: set[str] = set()
    for path in RAW_DIR.glob("*.json"):
        if not path.name.startswith(("borrowing_", "lending_")):
            continue
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for record in _records(body):
            value = str(record.get("enduser_id") or "").strip()
            if value and value != "0":
                found.add(value)
    return found


def date_windows(months: int, chunk_days: int) -> Iterator[tuple[date, date]]:
    """Walk backwards in fixed slices.

    The archives have no pagination and no documented size cap, so an
    unbounded range can return an unbounded response. The docs warn to "be a
    little careful with the span of the date interval" — chunking is the
    adapter-side answer, rehearsed here.
    """
    end = date.today()
    earliest = end - timedelta(days=int(months * 30.44))
    while end > earliest:
        start = max(earliest, end - timedelta(days=chunk_days))
        yield start, end
        end = start - timedelta(days=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sigel", default=os.environ.get(ENV_SIGEL))
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--chunk-days", type=int, default=30)
    parser.add_argument(
        "--include-inbox",
        action="store_true",
        help="capture /inbox — it is NOT cleared by reading",
    )
    parser.add_argument(
        "--max-enduser",
        type=int,
        default=25,
        help="how many enduser_id values to resolve via /userrequests (Part 1b)",
    )
    args = parser.parse_args()

    api_key = os.environ.get(ENV_API_KEY)
    if not args.sigel or not api_key:
        sys.exit(
            f"Set {ENV_SIGEL} (sigel) and {ENV_API_KEY} (api-key), "
            f"or pass --sigel."
        )

    sigel = args.sigel
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Libris fixture capture")
    print(f"  base   : {BASE}")
    print(f"  sigel  : {sigel}")
    print(f"  output : {RAW_DIR}")
    print()

    with httpx2.Client(
        transport=ReadOnlyTransport(),
        base_url=BASE,
        headers={"api-key": api_key},  # header auth; Libris has no basic auth
        timeout=httpx2.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0),
        follow_redirects=False,
    ) as client:
        cap = Capture(client)

        print("Lending views (utlån — another library asks us):")
        for view in LENDING_VIEWS:
            cap.fetch(f"/illrequests/{sigel}/{view}", f"lending_{view}")

        print("\nBorrowing views (inlån — we ask another library):")
        for view in BORROWING_VIEWS:
            cap.fetch(f"/illrequests/{sigel}/{view}", f"borrowing_{view}")

        if args.include_inbox:
            print("  ! /inbox is not cleared by reading — see module docstring")
            cap.fetch(f"/illrequests/{sigel}/{INBOX_VIEW}", "borrowing_inbox")
        else:
            print("  - borrowing_inbox            skipped (use --include-inbox)")

        # /recent is an INCOMING view — it returns requests to us, i.e.
        # LENDING. Naming these "borrowing_*" was a bug: every record they
        # return has active_library == our sigel.
        print("\nMedia-type filtered /recent (lending; Part 15 needs Kopia):")
        for media in ("loan", "copy"):
            cap.fetch(
                f"/illrequests/{sigel}/recent?media_type={media}",
                f"lending_recent_{media}",
            )

        print(f"\nArchives — status-independent, {args.months} months "
              f"in {args.chunk_days}-day slices:")
        for view, label in (
            ("incoming_archive", "lending"),
            ("outgoing", "borrowing"),
        ):
            for start, end in date_windows(args.months, args.chunk_days):
                cap.fetch(
                    f"/illrequests/{sigel}/{view}"
                    f"?start_date={start:%Y-%m-%d}&end_date={end:%Y-%m-%d}",
                    f"{label}_archive_{start:%Y%m%d}_{end:%Y%m%d}",
                )

        print("\nLibrary directory (Part 10 — library_accounts provisioning):")
        # The standalone library object and the receiving_library object
        # embedded in an ILL request have different field sets. Both need
        # fixtures. all_libraries is deliberately omitted: ~5 200 records,
        # and the docs say it "should not be used too frequently".
        cap.fetch(f"/libraries/{sigel}/{sigel}", "library_self")

        print("\nUser requests (Libris Websearch — empty if not accepted):")
        cap.fetch(f"/userrequests/{sigel}", "userrequests_outstanding")

        # The outstanding queue is often empty. The archive form is the only
        # reliable route to the `user` OBJECT carrying `library_card`.
        for start, end in date_windows(args.months, args.chunk_days):
            cap.fetch(
                f"/userrequests/{sigel}"
                f"?start_date={start:%Y-%m-%d}&end_date={end:%Y-%m-%d}",
                f"userrequests_archive_{start:%Y%m%d}_{end:%Y%m%d}",
            )

        # Part 1b — resolve enduser_id -> library_card.
        #
        # TRAP: `user_id` is endpoint-scoped. The parameter below is named
        # user_id, but /userrequests means by that its OWN user id — the
        # Websearch account, which /illrequests exposes as `enduser_id`.
        # It is NOT ill_requests[].user_id (the library card); the two sets
        # share no values across 1 620 records. Feed it enduser_id.
        enduser_ids = harvest_enduser_ids()
        if enduser_ids:
            print(f"\nResolving {min(len(enduser_ids), args.max_enduser)} of "
                  f"{len(enduser_ids)} enduser_id values (Part 1b):")
            for enduser_id in sorted(enduser_ids)[: args.max_enduser]:
                cap.fetch(
                    f"/userrequests/{sigel}?user_id={enduser_id}",
                    f"userrequest_enduser_{enduser_id}",
                )
        else:
            print("\n  - no enduser_id values found in the ILL corpus")

        summarise(cap.results, sigel)

        # Prove the guard is live rather than assuming it.
        try:
            client.post(f"/illrequests/{sigel}/1", data={"action": "read"})
        except RuntimeError as exc:
            print(f"\nWrite guard: OK ({exc})")
        else:
            sys.exit("\nFAIL: a write was not blocked — do not trust this run")

    return 0


def summarise(results: list[dict[str, Any]], sigel: str) -> None:
    """Print the deliverable: what the corpus now covers, and what it lacks."""
    ok = [r for r in results if r["count"] is not None]
    total = sum(r["count"] for r in ok)
    with_records = [r for r in ok if r["count"]]

    print("\n" + "=" * 66)
    print(f"Captured {total} records across {len(with_records)}/{len(results)} "
          f"endpoints that returned data")

    failed = [r for r in results if r["count"] is None]
    if failed:
        print("\nFailed / non-JSON:")
        for r in failed:
            print(f"  {r['name']:<34} {r['note']}")

    lending = sum(r["count"] for r in with_records if r["name"].startswith("lending"))
    borrowing = sum(
        r["count"] for r in with_records if r["name"].startswith("borrowing")
    )
    print(f"\nBy direction:  lending(utlån)={lending}  borrowing(inlån)={borrowing}")

    if lending == 0:
        print("  ! No lending records. Ambiguous between 'no activity' and")
        print("    'wrong/unregistered sigel' — an unknown sigel returns empty,")
        print("    NOT an error. See docs/further-audit-hal.md.")

    media = sorted({m for r in with_records for m in r.get("media_types", [])})
    print(f"\nmedia_type_code values seen: {media or 'NONE'}")
    if "2" not in media:
        print("  ! No Kopia record captured — Part 15 stays blocked.")

    codes = sorted({c for r in with_records for c in r.get("status_codes", [])})
    print(f"status_code values seen    : {codes or 'NONE'}")
    print("  Map on *_code, never on the Swedish label: live xstatus returns")
    print("  'Oläst' where the documentation says 'Ej läst'.")

    # Part 1b — the question that decides what the MVP is.
    patron = sum(r.get("with_patron", 0) for r in with_records)
    print(f"\nPart 1b — records with a populated 'user' field: {patron}/{total}")
    if total and patron == 0:
        print("  ! No patron identifier in ANY record. If this holds across a")
        print("    larger corpus, automatic borrowing provisioning is impossible")
        print("    and the MVP is a staff-mediated queue. Escalate before Part 6.")

    print("\nNext: sanitise before committing —")
    print("  uv run scripts/sanitize_fixtures.py")
    print("=" * 66)


if __name__ == "__main__":
    raise SystemExit(main())
