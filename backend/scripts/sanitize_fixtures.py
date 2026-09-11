"""Convert captured Libris payloads into committable fixtures.

Roadmap Part 1c.

Reads ``tests/fixtures/libris/_raw/`` (gitignored, contains live patron data)
and writes sanitised fixtures to ``tests/fixtures/libris/``.

Three independent safeguards, in order:

1. ``KNOWN_KEYS`` — a tripwire. Every key must have been consciously
   classified by a human. An unrecognised key halts the run, so a field
   Libris adds later cannot be committed unexamined.
2. ``PII_FIELDS`` — the redaction map. Replaces values with synthetic ones
   of the same type and rough shape, so fixtures stay useful for parser
   tests while being harmless.
3. ``assert_clean`` — a post-hoc scan of the output for identifier-shaped
   strings that survived, scoped to fields where such a match would be
   genuinely suspicious.

Constants are derived from real captured data via ``discover_fields.py``.
Re-run that script whenever the corpus grows; do not hand-edit blindly.

    uv run scripts/sanitize_fixtures.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any, Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "tests" / "fixtures" / "libris" / "_raw"
OUT = ROOT / "tests" / "fixtures" / "libris"

# ---------------------------------------------------------------------------
# PII_FIELDS — the redaction map.
#
# Paths use "[]" to mean "every element of this array". Generators receive a
# per-file index so values stay distinct but deterministic.
#
# Reviewed against 1 621 real records. discover_fields.py proposed 50 paths;
# ~30 were false positives (ISBN-13 and epoch timestamps match the
# personnummer pattern; "allow_userrequests" matches the "user" key rule).
# Those are deliberately absent below.
# ---------------------------------------------------------------------------
PII_FIELDS: dict[str, Callable[[int], Any]] = {
    # --- patron / end user -------------------------------------------------
    # Empty in all 1 620 records to date, but redact regardless: a later
    # capture may populate it, and this is the field Part 1b turns on.
    "ill_requests[].user": lambda i: f"SYNTHETIC-{1000 + i}",
    "ill_requests[].user_id": lambda i: f"{900000 + i}",
    "ill_requests[].enduser_id": lambda i: "0",
    "ill_requests[].libris_enduser_request_id": lambda i: "0",
    # All 15 end_user fields are null in the current corpus. They are the
    # Libris Websearch block and will populate for end-user requests.
    "ill_requests[].end_user.user_id": lambda i: f"{900000 + i}",
    "ill_requests[].end_user.first_name": lambda i: "Test",
    "ill_requests[].end_user.last_name": lambda i: f"Testsson {i}",
    "ill_requests[].end_user.email": lambda i: f"test{i}@example.invalid",
    "ill_requests[].end_user.phone": lambda i: f"070-000{i:04d}",
    "ill_requests[].end_user.mobile": lambda i: f"070-000{i:04d}",
    "ill_requests[].end_user.institution_phone": lambda i: f"070-000{i:04d}",
    "ill_requests[].end_user.library_card": lambda i: f"SYNTHETIC-{1000 + i}",
    "ill_requests[].end_user.address": lambda i: "Testgatan 1",
    "ill_requests[].end_user.zip_code": lambda i: "000 00",
    "ill_requests[].end_user.city": lambda i: "Teststad",
    "ill_requests[].end_user.institution": lambda i: "Testinstitution",
    "ill_requests[].end_user.approved_by": lambda i: "op",
    # --- staff identifier --------------------------------------------------
    # Initials of the librarian who created the request (1 620/1 620).
    # Identifies a natural person, so it is personal data under GDPR.
    "ill_requests[].operator": lambda i: "op",
    # --- free text ---------------------------------------------------------
    # Emptied, not scrubbed. Observed in the real corpus: 4 messages contain
    # personnummer-shaped strings and 2 recipient responses contain email
    # addresses. No key-name heuristic catches that, so the only safe
    # treatment of unconstrained prose is removal.
    "ill_requests[].message": lambda i: "",
    "ill_requests[].recipients[].response": lambda i: "",
    # --- library contact people --------------------------------------------
    # A named individual at the library, not an institutional mailbox.
    "libraries[].contact_person": lambda i: f"Testsson, Test {i}",
    "libraries[].email_contact_person": lambda i: f"test{i}@example.invalid",
    "libraries[].phone_contact_person": lambda i: f"070-000{i:04d}",
    # The library switchboard is institutional rather than personal, but a
    # synthetic number costs the fixture nothing and the general/contact
    # distinction blurs in dirty directory data. Defence in depth.
    "libraries[].phone": lambda i: f"070-000{i:04d}",
    # Institutional mailboxes in principle — but 1 343/1 620 observed values
    # are firstname.lastname@domain, i.e. personal in practice.
    "ill_requests[].receiving_library.email": lambda i: f"lib{i}@example.invalid",
    "libraries[].email_general": lambda i: f"lib{i}@example.invalid",
    "libraries[].email_replies": lambda i: f"lib{i}@example.invalid",
    "libraries[].email_requests": lambda i: f"lib{i}@example.invalid",
}

# ---------------------------------------------------------------------------
# KNOWN_KEYS — the tripwire.
#
# Every leaf key observed in the corpus, consciously classified. NOT used for
# redaction: its only job is to halt the run when Libris introduces a field
# nobody has looked at yet.
#
# Regenerate with: uv run scripts/discover_fields.py --emit
# ---------------------------------------------------------------------------
KNOWN_KEYS = {
    # envelope
    "count", "data_source", "data_type", "result_type", "library_code",
    "start_date", "end_date", "ill_requests", "libraries", "user_requests",
    # identifiers
    "request_id", "lf_number", "bib_id", "external_id", "test_url",
    "request_type", "library_id",
    # concurrency
    "last_modified",
    # status label/code pairs
    "status", "status_code", "xstatus", "xstatus_code",
    "local_status", "local_status_code", "media_type", "media_type_code",
    "delivery_type", "delivery_type_code",
    "processing_time", "processing_time_code",
    # parties and routing
    "requesting_library", "active_library", "receiving_library",
    "recipients", "recipient_count", "is_active_library", "location",
    "reserve", "response", "response_id", "response_date",
    # library directory
    "name", "department", "address", "address1", "address2", "address3",
    "zip_code", "city", "country", "country_code", "open_hours",
    "email", "email_general", "email_replies", "email_requests",
    "email_contact_person", "contact_person", "phone", "phone_contact_person",
    "fax", "fax_general", "fax_replies", "fax_requests",
    "bibsam", "BIBSAM", "NORDKVIK", "NORFRI",
    "normal_delivery", "fast_delivery", "express_delivery",
    "fax_delivery", "ftp_delivery",
    "closed", "closed_from", "closed_until", "closed_reason",
    "policy", "policy_userrequests", "prices",
    "allow_userrequests", "allow_userrequests_journal_articles",
    "userrequests_closed", "userrequests_closed_from",
    "userrequests_closed_until", "userrequests_closed_reason",
    # bibliographic
    "author", "title", "place_of_publication", "publisher", "year",
    "imprint", "isbn_issn", "pages",
    "author_of_article", "title_of_article", "journal_article",
    "volume_designation",
    # patron / end user
    "user", "user_id", "operator", "enduser_id",
    "libris_enduser_request_id", "end_user",
    "first_name", "last_name", "mobile", "library_card",
    "institution", "institution_phone", "institution_delivery",
    "home_delivery", "approved", "approved_by", "approval_date",
    # dates
    "arrival_date", "sign_date", "due_date", "renewal_date", "renewal_count",
    "return_date", "sendback_date",
    # misc
    "message",
}

# ---------------------------------------------------------------------------
# assert_clean — post-hoc scan.
#
# Scoped by field. A blanket scan is useless here: ISBN-13 values, the epoch
# last_modified and lf_number ("Hal-260908-0002") all match the personnummer
# pattern, so an unscoped check aborts on every legitimate file.
# ---------------------------------------------------------------------------
PERSONNUMMER = re.compile(r"\b\d{6,8}[-+]?\d{4}\b")
PHONE = re.compile(r"\b0\d{1,3}[-\s]?\d{5,8}\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# Fields whose values legitimately look like identifiers.
SHAPE_EXEMPT = {
    "isbn_issn",        # ISBN-13 matches the personnummer pattern
    "last_modified",    # unix epoch, 10 digits
    "lf_number",        # Hal-260908-0002
    "request_id", "bib_id", "library_id", "user_id",
    "title", "title_of_article", "author_of_article", "journal_article",
    "volume_designation", "pages", "imprint", "publisher",
    "place_of_publication", "policy", "policy_userrequests", "prices",
    "open_hours", "test_url",
    "arrival_date", "sign_date", "due_date", "renewal_date", "return_date",
    "sendback_date", "response_date", "closed_from", "closed_until",
    "userrequests_closed_from", "userrequests_closed_until",
    "start_date", "end_date",
}

SYNTHETIC_MARKERS = ("example.invalid", "SYNTHETIC-", "070-000")


def set_path(obj: Any, dotted: str, value: Any) -> None:
    """Assign into a nested structure. ``a[].b`` applies to every element of ``a``."""
    head, _, rest = dotted.partition(".")

    if head.endswith("[]"):
        array = obj.get(head[:-2]) if isinstance(obj, dict) else None
        if isinstance(array, list):
            for item in array:
                if rest:
                    set_path(item, rest, value)
        return

    if not isinstance(obj, dict):
        return

    if rest:
        child = obj.get(head)
        if isinstance(child, dict):
            set_path(child, rest, value)
        elif isinstance(child, list):
            for item in child:
                set_path(item, rest, value)
        return

    # Only overwrite keys that exist — never invent a field.
    #
    # Critically: preserve absence. If the source value is empty, null or the
    # "0" sentinel, leave it exactly as it is. Fill rate IS data — replacing
    # an empty `user` with a synthetic barcode would manufacture a patron
    # identifier that Libris never sent, and silently invalidate the Part 1b
    # analysis that decides what the MVP is.
    if head in obj and obj[head] not in (None, "", "0"):
        obj[head] = value


def check_unknown_keys(obj: Any, path: str = "") -> list[str]:
    """Report any key that has not been consciously classified."""
    unknown: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key not in KNOWN_KEYS:
                unknown.append(f"{path}.{key}".lstrip("."))
            unknown += check_unknown_keys(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for item in obj:
            unknown += check_unknown_keys(item, path)
    return unknown


def scan_values(obj: Any, findings: list[str], path: str = "") -> None:
    """Walk leaves and flag identifier-shaped strings outside exempt fields."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            scan_values(value, findings, f"{path}.{key}".lstrip("."))
        return
    if isinstance(obj, list):
        for item in obj:
            scan_values(item, findings, path)
        return

    leaf = path.rsplit(".", 1)[-1]
    if leaf in SHAPE_EXEMPT or not isinstance(obj, str) or not obj:
        return

    for label, pattern in (
        ("personnummer", PERSONNUMMER),
        ("phone", PHONE),
        ("email", EMAIL),
    ):
        for match in pattern.findall(obj):
            if any(marker in match for marker in SYNTHETIC_MARKERS):
                continue
            # Report the field and pattern class, never the value itself.
            findings.append(f"{path}: {label}-shaped value survived")
            return


def main() -> int:
    if not RAW.exists():
        print(f"No captured payloads at {RAW}")
        print("Run: uv run scripts/collect_endpoints_response.py")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    blocked: list[str] = []
    written = 0

    for index, src in enumerate(sorted(RAW.glob("*.json")), start=1):
        try:
            payload = json.loads(src.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            blocked.append(f"{src.name}: unreadable ({exc})")
            continue

        unknown = check_unknown_keys(payload)
        if unknown:
            blocked.append(f"{src.name}: unclassified {sorted(set(unknown))[:6]}")
            continue

        for dotted, generate in PII_FIELDS.items():
            set_path(payload, dotted, generate(index))

        findings: list[str] = []
        scan_values(payload, findings)
        if findings:
            blocked.append(f"{src.name}: {sorted(set(findings))[:4]}")
            continue

        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        (OUT / src.name).write_text(text + "\n", encoding="utf-8")
        written += 1
        print(f"  ✓ {src.name}")

    print(f"\nSanitised {written}/{written + len(blocked)} files")

    if blocked:
        print("\nREFUSED — nothing was written for these:")
        for item in blocked:
            print(f"  {item}")
        print("\nClassify new keys in KNOWN_KEYS, add any personal field to")
        print("PII_FIELDS, then re-run. Do not weaken the checks to get past this.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
