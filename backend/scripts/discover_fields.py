"""Derive sanitiser constants from captured payloads.

Roadmap Part 1c. Reads ``tests/fixtures/libris/_raw/`` and emits starting
points for ``KNOWN_KEYS`` and ``PII_FIELDS`` in ``sanitize_fixtures.py``.

    uv run scripts/discover_fields.py            # report
    uv run scripts/discover_fields.py --emit     # printable constants

What this does and does not do
------------------------------
It enumerates every path that actually occurs and flags candidates by
heuristic. It **proposes**; a human **classifies**. Never paste the emitted
PII list in unread: a key named ``message`` or ``response`` is free text and
can contain anything regardless of what the sampled values happen to show.

Values are never printed — only masked shapes (``Aa… a…@aa.aa``), so running
this cannot leak personal data into a terminal, a log or a transcript.
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
from typing import Any, Iterator

RAW = pathlib.Path(__file__).resolve().parent.parent / "tests/fixtures/libris/_raw"

# --- heuristics -------------------------------------------------------------
# Key names that suggest a natural person. Deliberately broad: a false
# positive costs a moment's review, a false negative commits PII.
PERSON_KEY = re.compile(
    r"(user|patron|borrower|operator|contact|person|name|email|mail|phone"
    r"|mobile|address|card|zip|city|birth|personnummer|signature)",
    re.I,
)

# Keys whose values are unconstrained prose.
FREE_TEXT_KEY = re.compile(r"(message|note|response|comment|added|remark|reason)", re.I)

# Value patterns worth flagging wherever they appear.
VALUE_PATTERNS = {
    "personnummer": re.compile(r"\b\d{6,8}[-+]?\d{4}\b"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "phone": re.compile(r"\b0\d{1,3}[-\s]?\d{5,8}\b"),
    "url": re.compile(r"https?://"),
}

# Institutional identifiers that look personal but are not.
NOT_PERSONAL = {
    "library_code",
    "requesting_library",
    "active_library",
    "library_id",
    "name",  # library name — but see receiving_library.email note in the report
}


def mask(value: Any) -> str:
    """Collapse a value to a character-class shape. Never returns real content."""
    text = str(value)
    text = re.sub(r"[A-ZÅÄÖ]", "A", text)
    text = re.sub(r"[a-zåäö]", "a", text)
    text = re.sub(r"\d", "9", text)
    return re.sub(r"(.)\1{2,}", r"\1…", text)[:36]


class Field:
    __slots__ = ("path", "seen", "nonempty", "types", "shapes", "hits", "leaf")

    def __init__(self, path: str) -> None:
        self.path = path
        self.leaf = path.rsplit(".", 1)[-1].replace("[]", "")
        self.seen = 0
        self.nonempty = 0
        self.types: set[str] = set()
        self.shapes: collections.Counter[str] = collections.Counter()
        self.hits: collections.Counter[str] = collections.Counter()

    def observe(self, value: Any) -> None:
        self.seen += 1
        self.types.add(type(value).__name__)
        if value in (None, ""):
            return
        self.nonempty += 1
        self.shapes[mask(value)] += 1
        text = str(value)
        for label, pattern in VALUE_PATTERNS.items():
            if pattern.search(text):
                self.hits[label] += 1

    @property
    def risk(self) -> tuple[str, str]:
        """(level, reason) — the proposal a human then accepts or rejects."""
        if self.hits.get("personnummer"):
            return "PII", "personnummer pattern in values"
        if self.leaf in NOT_PERSONAL and not self.hits.get("email"):
            return "ok", "institutional identifier"
        if self.hits.get("email"):
            return "PII", f"email pattern in {self.hits['email']} values"
        if self.hits.get("phone"):
            return "PII", f"phone pattern in {self.hits['phone']} values"
        if PERSON_KEY.search(self.leaf):
            return "PII", f"key name suggests a person ({self.leaf})"
        if FREE_TEXT_KEY.search(self.leaf):
            return "review", "free text — may contain anything"
        if self.hits.get("url"):
            return "review", "contains a URL — never dereference"
        return "ok", ""


def walk(obj: Any, fields: dict[str, Field], prefix: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}".lstrip(".")
            if isinstance(value, (dict, list)):
                walk(value, fields, path)
            else:
                fields.setdefault(path, Field(path)).observe(value)
    elif isinstance(obj, list):
        for item in obj:
            walk(item, fields, f"{prefix}[]")


def load() -> tuple[dict[str, Field], int]:
    fields: dict[str, Field] = {}
    files = 0
    for path in sorted(RAW.glob("*.json")):
        try:
            walk(json.loads(path.read_text(encoding="utf-8")), fields)
            files += 1
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  ! skipped {path.name}: {exc}")
    return fields, files


def report(fields: dict[str, Field], files: int) -> None:
    buckets: dict[str, list[Field]] = collections.defaultdict(list)
    for field in fields.values():
        buckets[field.risk[0]].append(field)

    print(f"Scanned {files} files, {len(fields)} distinct paths\n")

    for level, title in (
        ("PII", "MUST redact — add to PII_FIELDS"),
        ("review", "NEEDS a human decision"),
        ("ok", "No personal data detected — KNOWN_KEYS only"),
    ):
        group = sorted(buckets.get(level, []), key=lambda f: f.path)
        if not group:
            continue
        print(f"=== {title} ({len(group)}) ===")
        for field in group:
            reason = field.risk[1]
            fill = f"{field.nonempty}/{field.seen}"
            if level == "ok":
                print(f"  {field.path:<52} {fill}")
                continue
            shape = field.shapes.most_common(1)
            shape_text = shape[0][0] if shape else "—"
            print(f"  {field.path:<52} {fill:<12} {shape_text:<24} {reason}")
        print()

    empty = [f for f in fields.values() if f.nonempty == 0 and f.seen]
    if empty:
        print(f"=== Always empty in this corpus ({len(empty)}) ===")
        print("  Classify anyway — a later capture may populate them.")
        for field in sorted(empty, key=lambda f: f.path):
            print(f"  {field.path:<52} 0/{field.seen}")
        print()


def emit(fields: dict[str, Field]) -> None:
    """Print constants ready to paste — after review, not instead of it."""
    print("# " + "=" * 72)
    print("# Generated by discover_fields.py — REVIEW BEFORE USE.")
    print("# " + "=" * 72)
    print("\nKNOWN_KEYS = {")
    for leaf in sorted({f.leaf for f in fields.values()}):
        print(f'    "{leaf}",')
    print("}\n")

    print("PII_FIELDS = {")
    for field in sorted(fields.values(), key=lambda f: f.path):
        level, reason = field.risk
        if level != "PII":
            continue
        leaf = field.leaf
        if "email" in leaf:
            gen = 'lambda i: f"test{i}@example.invalid"'
        elif "phone" in leaf or "mobile" in leaf or "fax" in leaf:
            gen = 'lambda i: f"070-000{i:04d}"'
        elif leaf.endswith("_id") or "card" in leaf:
            gen = 'lambda i: f"{900000 + i}"'
        elif "name" in leaf or "person" in leaf:
            gen = 'lambda i: f"Testsson, Test {i}"'
        else:
            gen = 'lambda i: f"SYNTHETIC-{1000 + i}"'
        print(f'    "{field.path}": {gen},  # {reason}')
    print("}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emit", action="store_true", help="print constants")
    args = parser.parse_args()

    if not RAW.exists():
        print(f"No captured payloads at {RAW}")
        print("Run: uv run scripts/collect_endpoints_response.py")
        return 1

    fields, files = load()
    if not fields:
        return 1

    if args.emit:
        emit(fields)
    else:
        report(fields, files)
        print("Next: review, then `--emit` and paste into sanitize_fixtures.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
