"""Measure the fixture corpus against the LIBRISintegrationer requirements.

Roadmap Part 1a/1c — the report that unblocks Part 3 and answers Part 1b.

Reads sanitised fixtures from ``tests/fixtures/libris/`` and reports, per
record:

* coverage of the nine required fields, split by direction;
* the ``*_code`` / label matrix that the mapping profile is built from;
* observed date formats;
* whether a local patron identifier is ever present (Part 1b).

    uv run scripts/field_coverage.py

Exits non-zero when a blocking gap remains, so it can gate CI.

Why record-level
----------------
An earlier version counted *files*. A single file holds up to 509 records,
so "34/34 ALWAYS" described the corpus directory rather than the data.
Everything here counts records inside ``ill_requests[]``.

Conditional expectations
------------------------
Article fields are only meaningful for ``Kopia`` (``media_type_code == "2"``).
Reporting ``title_of_article`` as "missing" across loan records would be
noise, so expectations are evaluated within the relevant subset.
"""

from __future__ import annotations

import collections
import json
import pathlib
import re
from typing import Any, Iterable

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "libris"

# --- the nine fields required by LIBRISintegrationer ------------------------
# Real Libris paths. Multiple candidates mean "any of these satisfies it".
REQUIRED: dict[str, dict[str, Any]] = {
    "Librisnr (beställnings-ID)": {"paths": ["lf_number", "request_id"]},
    "aktivt lånebibliotek": {"paths": ["active_library"]},
    "författare": {"paths": ["author"]},
    "titel": {"paths": ["title"]},
    "artikeltitel": {"paths": ["title_of_article"], "only_when": ("media_type_code", "2")},
    "år": {"paths": ["year"]},
    "lån/kopia": {"paths": ["media_type_code"]},
    "låntagare": {"paths": ["user"]},  # user_id is Libris-internal, not local
    "status": {"paths": ["status_code"]},
}

# Label/code pairs. Mapping is done on the code, never the Swedish label.
CODE_FIELDS = [
    "status",
    "xstatus",
    "media_type",
    "local_status",
    "delivery_type",
    "processing_time",
]

DATE_FIELDS = [
    "arrival_date",
    "sign_date",
    "due_date",
    "renewal_date",
    "return_date",
    "sendback_date",
    "last_modified",
]

# What the official documentation claims, so live contradictions surface.
# api_doc.md §6.4: docs say xstatus resets to "Ej läst"; live returns "Oläst".
DOCUMENTED_LABELS = {"xstatus": {"Ej läst", "Läst"}}

# Free-text fields that sanitize_fixtures.py empties wholesale, because
# observed values contain personnummer- and email-shaped strings. Their fill
# rate is therefore NOT measurable from sanitised fixtures — a 0 here means
# "redacted", not "absent in Libris". Measure these against _raw/ if needed.
EMPTIED_BY_SANITISER = {"message", "response"}


def shape(value: Any) -> str:
    text = str(value)
    text = re.sub(r"[A-ZÅÄÖ]", "A", text)
    text = re.sub(r"[a-zåäö]", "a", text)
    text = re.sub(r"\d", "9", text)
    return re.sub(r"(.)\1{2,}", r"\1…", text)[:24]


def filled(value: Any) -> bool:
    """Libris encodes absence three ways: "", null and the sentinel "0"."""
    return value not in (None, "", "0")


def load_records() -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    notes: list[str] = []

    for path in sorted(FIXTURES.glob("*.json")):
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            notes.append(f"{path.name}: unreadable ({exc})")
            continue

        local = body.get("library_code")
        view = path.stem
        for record in body.get("ill_requests") or []:
            if not isinstance(record, dict):
                continue
            # Direction is derived from the payload, not the view
            # (api_doc.md §6.5): requesting_library == us means we borrow.
            record["_direction"] = (
                "BORROWING" if record.get("requesting_library") == local else "LENDING"
            )
            record["_view"] = view
            records.append(record)

    return records, notes


def coverage(records: list[dict[str, Any]]) -> None:
    print(f"{'Required field':<28}{'Applies':>9}{'Present':>9}  Verdict")
    print("-" * 78)

    blocking: list[str] = []

    for label, spec in REQUIRED.items():
        subset = records
        note = ""
        if "only_when" in spec:
            key, value = spec["only_when"]
            subset = [r for r in records if r.get(key) == value]
            note = f" (of {key}={value})"

        applies = len(subset)
        present = sum(
            1 for r in subset if any(filled(r.get(p)) for p in spec["paths"])
        )

        if applies == 0:
            verdict = "NO DATA — subset is empty"
            blocking.append(f"{label}: no applicable records{note}")
        elif present == applies:
            verdict = "ALWAYS"
        elif present == 0:
            verdict = "MISSING — never populated"
            blocking.append(f"{label}: 0/{applies}")
        else:
            pct = 100 * present / applies
            verdict = f"SOMETIMES — {pct:.0f}%, {applies - present} without"

        print(f"{label:<28}{applies:>9}{present:>9}  {verdict}{note}")

    if blocking:
        print("\n  Blocking gaps:")
        for item in blocking:
            print(f"    - {item}")


def by_direction(records: list[dict[str, Any]]) -> None:
    counts = collections.Counter(r["_direction"] for r in records)
    print(f"\nBy direction:  BORROWING(inlån)={counts['BORROWING']}  "
          f"LENDING(utlån)={counts['LENDING']}")

    # A record whose derived direction disagrees with the view it came from
    # is a data-quality signal, not noise. Report rather than silently trust.
    odd = [
        r for r in records
        if r["_view"].startswith("borrowing") and r["_direction"] == "LENDING"
        or r["_view"].startswith("lending") and r["_direction"] == "BORROWING"
    ]
    if odd:
        print(f"  ! {len(odd)} record(s) whose payload direction disagrees with "
              f"the source view:")
        for r in odd[:5]:
            print(f"      {r.get('lf_number')} in {r['_view']}: "
                  f"requesting_library={r.get('requesting_library')!r} "
                  f"-> {r['_direction']}")

    if counts["LENDING"] == 0:
        print("  ! No lending records. Ambiguous between 'no activity' and")
        print("    'wrong/unregistered sigel' — an unknown sigel returns empty,")
        print("    NOT an error. See docs/further-audit-hal.md. Blocks Part 10.")


def code_matrix(records: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 78)
    print("Code / label matrix — the mapping profile is built on codes")
    print("=" * 78)

    for field in CODE_FIELDS:
        pairs = collections.Counter(
            (str(r.get(f"{field}_code")), str(r.get(field)))
            for r in records
            if filled(r.get(field)) or filled(r.get(f"{field}_code"))
        )
        if not pairs:
            print(f"\n{field}: no data")
            continue

        print(f"\n{field}:")
        by_code: dict[str, set[str]] = collections.defaultdict(set)
        for (code, label), count in sorted(pairs.items()):
            print(f"    {code:>4} = {label:<24} {count:>6}")
            by_code[code].add(label)

        # One code mapping to several labels means the code is not a key.
        ambiguous = {c: labels for c, labels in by_code.items() if len(labels) > 1}
        if ambiguous:
            for code, labels in ambiguous.items():
                print(f"    ! code {code!r} maps to {len(labels)} labels: "
                      f"{sorted(labels)}")
            print(f"    -> {field}_code is NOT a usable key. Map on the label")
            print(f"       here, and record the exception in the mapping profile.")

        documented = DOCUMENTED_LABELS.get(field)
        if documented:
            live = {label for _, label in pairs}
            unexpected = live - documented
            if unexpected:
                print(f"    ! live labels contradict the documentation: "
                      f"{sorted(unexpected)} not in {sorted(documented)}")


def date_formats(records: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 78)
    print("Date formats — decides Part 3 storage types")
    print("=" * 78)

    for field in DATE_FIELDS:
        values = [r.get(field) for r in records if filled(r.get(field))]
        if not values:
            print(f"  {field:<18} 0 values — format still unobserved")
            continue
        shapes = collections.Counter(shape(v) for v in values)
        rendered = ", ".join(f"{s} ({n})" for s, n in shapes.most_common(3))
        print(f"  {field:<18} {len(values):>5} values   {rendered}")

    print("\n  last_modified is a unix epoch string: store opaque, resend")
    print("  verbatim as the POST timestamp. Never parse and reserialise.")


def patron_summary(records: list[dict[str, Any]]) -> bool:
    """Part 1b — the question that decides what the MVP is."""
    print("\n" + "=" * 78)
    print("Part 1b — local patron identifier")
    print("=" * 78)

    borrowing = [r for r in records if r["_direction"] == "BORROWING"]
    with_user = [r for r in borrowing if filled(r.get("user"))]
    with_libris_id = [r for r in borrowing if filled(r.get("user_id"))]
    end_user = [
        r for r in borrowing
        if isinstance(r.get("end_user"), dict)
        and any(filled(v) for v in r["end_user"].values())
    ]

    total = len(borrowing)
    print(f"  borrowing records            {total}")
    print(f"  with 'user' (local patron)   {len(with_user)}")
    print(f"  with 'user_id' (Libris)      {len(with_libris_id)}")
    print(f"  with populated end_user      {len(end_user)}")

    if total and not with_user:
        print("\n  ! No local patron identifier in ANY borrowing record.")
        print("    'user_id' is Libris-internal with no established FOLIO mapping,")
        print("    and exact matching against mod-users is mandatory.")
        print("    => Automatic borrowing provisioning is not possible.")
        print("    => The MVP is a staff-mediated queue unless this changes.")
        print("    Escalate before Part 6. See api_impact_on_roadmap.md §4.2.")
        return False
    return True


def media_split(records: list[dict[str, Any]]) -> bool:
    counts = collections.Counter(r.get("media_type_code") for r in records)
    labels = {"1": "Lån", "2": "Kopia"}
    print("\nMedia types:")
    for code, count in sorted(counts.items(), key=lambda kv: str(kv[0])):
        print(f"    {code} = {labels.get(str(code), '?'):<8} {count:>6}")
    if not counts.get("2"):
        print("  ! No Kopia records — Part 15 (article workflow) stays blocked.")
        return False
    return True


def main() -> int:
    if not FIXTURES.exists():
        print(f"No fixtures at {FIXTURES}")
        print("Run collect_endpoints_response.py then sanitize_fixtures.py")
        return 1

    records, notes = load_records()
    for note in notes:
        print(f"  ! {note}")

    if not records:
        print("No records found. Has sanitize_fixtures.py run?")
        return 1

    files = len(list(FIXTURES.glob("*.json")))
    print(f"Fixtures: {files} files, {len(records)} records")
    print(f"Note: {', '.join(sorted(EMPTIED_BY_SANITISER))} are emptied by the")
    print("sanitiser (free text). Their fill rate is not measurable here.\n")

    coverage(records)
    by_direction(records)
    has_copy = media_split(records)
    code_matrix(records)
    date_formats(records)
    has_patron = patron_summary(records)

    print("\n" + "=" * 78)
    unresolved = [
        label for label, ok in
        (("Part 1b patron identifier", has_patron), ("Part 15 Kopia fixture", has_copy))
        if not ok
    ]
    if unresolved:
        print("Unresolved blocking items: " + ", ".join(unresolved))
        return 1
    print("No blocking gaps detected in this corpus.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
