"""Fake Libris ILL API — fixtures plus generated records.

Run on a different port so both simulators can be up at once::

    uvicorn ill_bridge.providers.fake.server_faker:app --port 9001
    ILL_LIBRIS_BASE_URL=http://localhost:9001/librisfjarrlan/api

Fixtures win when present; generation fills the gaps. Records are seeded **per
record**, so output is stable across runs and inserting one does not shift
every value after it.

Behaviours copied from the real API because they are load-bearing:

* an unknown sigel returns ``count: 0``, never a 404 — a misconfigured library
  is indistinguishable from a quiet week, which the UI must alert on;
* ``api-key`` is a header, not a bearer token and not basic auth;
* there is no pagination and no request-creation endpoint;
* ``last_modified`` is an opaque epoch string used for optimistic concurrency.
"""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from faker import Faker
from fastapi import FastAPI, Header, HTTPException, Query

FIXTURES = Path(__file__).parents[3] / "tests/fixtures/libris"

# Verified against 2 189 real records — see docs/part1_conclusion.md §2.
# Mapping is done on the code; the label is display only. Note `Oläst`: the
# official documentation says "Ej läst", the live API returns "Oläst".
STATUS = {
    "1": "Uteliggande",
    "3": "Läst",
    "4": "Remitterad",
    "6": "Negativt svar",
    "9": "Reserverad",
    "10": "Levererad",
    "13": "Makulerad",
}
XSTATUS = {"1": "Oläst", "2": "Läst"}
MEDIA_TYPE = {"1": "Lån", "2": "Kopia"}
DELIVERY_TYPE = {"1": "Post", "3": "Ariel"}
LOCAL_STATUS = {
    "0": "",
    "1": "Anländ",
    "2": "Kvitterad",
    "5": "Återlämnad",
    "6": "Returnerad",
}
# Documented but never observed in the corpus. Generated on request so the
# mapping profile can be tested before real ones appear.
UNOBSERVED_STATUS = {"Reservation", "Avbeställd", "Ej avbeställd!"}

# Direction follows the payload, not the endpoint name: /recent and /incoming
# are LENDING views (another library asks us).
LENDING_VIEWS = {"incoming", "recent", "reservations", "cancellations"}

app = FastAPI(
    title="Fake Libris ILL API (fixtures + Faker)",
    description="Simulator. Serves sanitised fixtures and generated records.",
)


def _envelope(
    result_type: str,
    sigel: str,
    records: list[dict[str, Any]],
    data_type: str = "ill_requests",
) -> dict[str, Any]:
    return {
        "data_source": "illse",
        "data_type": data_type,
        "result_type": result_type,
        "library_code": sigel,
        "count": len(records),
        data_type: records,
    }


def _load_fixture(name: str, sigel: str | None = None) -> dict[str, Any] | None:
    """Load a fixture, but only if it belongs to the requested sigel.

    Without the sigel check the simulator would serve Hal's records for any
    library code, hiding the behaviour that matters most: an unknown sigel
    returns an empty envelope, so a misconfiguration is indistinguishable from
    a quiet week.
    """
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        return None
    fixture = json.loads(path.read_text(encoding="utf-8"))
    if sigel is not None and fixture.get("library_code") != sigel:
        return None
    return fixture


# Faker's sentence() uses the Latin lorem provider even under sv_SE, which
# produces no åäö and defeats the point of generating Swedish text. These are
# drawn from vocabulary observed in the real corpus.
TITLE_WORDS = (
    "färg",
    "arkitektur",
    "bibliotek",
    "handbok",
    "översikt",
    "studier",
    "utveckling",
    "samhälle",
    "hälsa",
    "miljö",
    "förändring",
    "årsbok",
    "vägar",
    "möjligheter",
    "människan",
    "språk",
    "återblick",
    "närvaro",
    "kunskap",
    "förhållanden",
    "väsen",
    "trädgård",
    "höst",
    "kärlek",
)
TITLE_PATTERNS = (
    "{a} och {b}",
    "{a}ens betydelse i nordisk {b}",
    "Om {a} : en studie i {b}",
    "{a} — {b} i förändring",
    "Den nya {a}en : {b} och framtiden",
)


def _swedish_title(rng: random.Random) -> str:
    a, b = rng.sample(TITLE_WORDS, 2)
    return rng.choice(TITLE_PATTERNS).format(a=a.capitalize(), b=b)


def _library(fake: Faker, sigel: str) -> dict[str, Any]:
    """An embedded library object. Fewer fields than /libraries returns."""
    return {
        "name": f"{fake.city()} {fake.random_element(['universitetsbibliotek', 'stadsbibliotek', 'högskolebibliotek'])}",
        "department": fake.random_element(["", "Fjärrlån", "Lånecentralen"]),
        "address1": fake.street_address(),
        "address2": None,
        "address3": None,
        "zip_code": fake.postcode(),
        "city": fake.city(),
        # example.invalid is reserved and unroutable — a generated address can
        # never accidentally reach a real mailbox.
        "email": f"fjarrlan@{sigel.lower()}.example.invalid",
        "fax": "fax",  # observed literal junk in the real directory
        "bibsam": fake.random_element(["1", "0"]),
    }


def generate_request(
    seq: int,
    sigel: str,
    *,
    direction: str = "BORROWING",
    status_code: str | None = None,
    media_type_code: str | None = None,
    unobserved_status: str | None = None,
) -> dict[str, Any]:
    """Build one record matching the observed shape.

    Seeded per record rather than globally: values stay stable across runs, and
    inserting or reordering records does not shift everything after it.
    """
    fake = Faker("sv_SE")
    Faker.seed(seq)
    rng = random.Random(seq)

    status_code = status_code or rng.choice(list(STATUS))
    media_type_code = media_type_code or rng.choice(list(MEDIA_TYPE))
    is_copy = media_type_code == "2"

    created = datetime.now(UTC) - timedelta(days=rng.randint(0, 400))
    other = fake.lexify("????", letters="ABCDEFGHKLMNOPRSTUVX").capitalize()
    requesting, active = (sigel, other) if direction == "BORROWING" else (other, sigel)

    # user_id is the library card number. 87% of real values are 8 digits in
    # the 50/60/70 series; ~13% are a 6-digit series whose meaning is still
    # unresolved. Reproduce both so matching logic meets the awkward case.
    if rng.random() < 0.87:
        user_id = f"{rng.choice([50, 60, 70])}{rng.randint(0, 999999):06d}"
    else:
        user_id = str(rng.randint(100089, 114908))

    record: dict[str, Any] = {
        "request_id": str(6_000_000 + seq),
        "lf_number": f"{requesting}-{created:%y%m%d}-{seq % 10000:04d}",
        "bib_id": str(rng.randint(1_000_000, 99_999_999)),
        "external_id": "",
        # Opaque epoch string. Store verbatim; never parse and reserialise.
        "last_modified": str(int(created.timestamp())),
        "status_code": status_code,
        "status": unobserved_status or STATUS[status_code],
        "xstatus_code": rng.choice(list(XSTATUS)),
        "xstatus": "",
        "local_status_code": "0",
        "local_status": "",
        "media_type_code": media_type_code,
        "media_type": MEDIA_TYPE[media_type_code],
        "delivery_type_code": "1",
        "delivery_type": DELIVERY_TYPE["1"],
        "processing_time_code": "1",
        "processing_time": "Normal",
        "request_type": "LF",
        "requesting_library": requesting,
        "active_library": active,
        "receiving_library": _library(fake, active),
        "recipients": [],
        "recipient_count": "1",
        # Real Libris titles carry ISBD punctuation and the statement of
        # responsibility; `author` is empty in ~59% of observed records.
        "title": f"{_swedish_title(rng)} / {fake.name()}.",
        "author": fake.name() if rng.random() < 0.41 else "",
        "place_of_publication": fake.city(),
        "publisher": f"{fake.last_name()} förlag",
        "year": str(rng.randint(1950, 2026)),
        "imprint": "  ",
        "isbn_issn": fake.isbn13()
        if not is_copy
        else str(rng.randint(10000000, 99999999)),
        "title_of_article": _swedish_title(rng) if is_copy else None,
        "author_of_article": fake.name() if is_copy else None,
        "pages": f"{rng.randint(1, 200)}-{rng.randint(201, 400)}" if is_copy else None,
        "volume_designation": f"{rng.randint(1, 60)}({rng.randint(1, 12)})"
        if is_copy
        else None,
        "journal_article": f"Tidskrift för {rng.choice(TITLE_WORDS)}"
        if is_copy
        else "",
        # Patron: `user` is empty in all 1 620 observed borrowing records.
        "user": "",
        "user_id": user_id,
        "operator": fake.user_name()[:3],
        "enduser_id": "0" if rng.random() < 0.92 else str(rng.randint(33506, 123486)),
        "libris_enduser_request_id": "0",
        "end_user": dict.fromkeys(
            [
                "user_id",
                "first_name",
                "last_name",
                "email",
                "phone",
                "mobile",
                "address",
                "zip_code",
                "city",
                "institution",
                "institution_phone",
                "library_card",
                "approved",
                "approved_by",
                "approval_date",
            ]
        ),
        "message": "",
        "test_url": f"http://internal.example.invalid/lf/{sigel}/{seq}",
        "arrival_date": None,
        "sign_date": None,
        "due_date": None,
        "renewal_date": None,
        "renewal_count": None,
        "return_date": None,
        "sendback_date": None,
    }
    record["xstatus"] = XSTATUS[record["xstatus_code"]]
    record["local_status"] = LOCAL_STATUS[record["local_status_code"]]
    return record

@app.get("/health")
async def health() -> dict[str, object]:
    fixtures = sorted(p.stem for p in FIXTURES.glob("*.json"))
    return {"status": "ok", "fixtures": len(fixtures), "fixture_dir": str(FIXTURES)}


@app.get("/librisfjarrlan/api/illrequests/{sigel}/{view}")
async def ill_requests(
    sigel: str,
    view: str,
    api_key: Annotated[str | None, Header(alias="api-key")] = None,
    media_type: Annotated[str | None, Query()] = None,
    generate: Annotated[int, Query(ge=0, le=5000)] = 0,
    status: Annotated[str | None, Query()] = None,
    fail: Annotated[int | None, Query()] = None,
) -> dict[str, Any]:
    """Serve a view. Fixtures first, generation on request.

    Query parameters beyond `media_type` are simulator-only:

    * ``generate=N`` — return N generated records instead of the fixture.
    * ``status=Reservation`` — force a status the real corpus never contained.
    * ``fail=429`` — return an error, for the Part 4 retry tests.
    """
    # Libris authenticates with an api-key header. No basic auth, no OAuth.
    if not api_key:
        raise HTTPException(401, "missing api-key header")

    if fail:
        raise HTTPException(fail, f"simulated upstream failure {fail}")

    direction = "LENDING" if view in LENDING_VIEWS else "BORROWING"

    if generate:
        media_code = {"loan": "1", "copy": "2"}.get(media_type or "")
        records = [
            generate_request(
                seq,
                sigel,
                direction=direction,
                media_type_code=media_code,
                status_code="1" if status in UNOBSERVED_STATUS else None,
                unobserved_status=status if status in UNOBSERVED_STATUS else None,
            )
            for seq in range(1, generate + 1)
        ]
        return _envelope(view, sigel, records)

    prefix = "lending" if direction == "LENDING" else "borrowing"
    suffix = f"_{media_type}" if media_type else ""
    fixture = _load_fixture(f"{prefix}_{view}{suffix}", sigel) or _load_fixture(
        f"{prefix}_{view}", sigel
    )

    # An unknown sigel or an empty queue returns an empty envelope, NOT a 404.
    # A misconfigured library therefore looks exactly like a quiet week, which
    # is why the UI needs a "no incoming in N days" alert.
    return fixture or _envelope(view, sigel, [])


@app.post("/librisfjarrlan/api/illrequests/{sigel}/{request_id}")
async def update_request(
    sigel: str,
    request_id: str,
    api_key: Annotated[str | None, Header(alias="api-key")] = None,
) -> dict[str, Any]:
    """Writes are refused.

    The real API accepts four actions (read, reserve, reserve-cancel,
    response) and has no undo. The simulator refuses them outright so an
    accidentally-pointed test cannot establish a habit the real API punishes.
    """
    if not api_key:
        raise HTTPException(401, "missing api-key header")
    raise HTTPException(
        501, "fake provider is read-only; writes are certified in roadmap Part 11"
    )


@app.get("/librisfjarrlan/api/libraries/{sigel}/{target}")
async def libraries(
    sigel: str,
    target: str,
    api_key: Annotated[str | None, Header(alias="api-key")] = None,
    generate: Annotated[int, Query(ge=0, le=5200)] = 0,
) -> dict[str, Any]:
    """Library directory. ``target`` may be a sigel, a comma list, or
    ``all_libraries`` (~5 200 records in production)."""
    if not api_key:
        raise HTTPException(401, "missing api-key header")

    if target == "all_libraries" and generate:
        records = []
        for seq in range(1, generate + 1):
            fake = Faker("sv_SE")
            Faker.seed(10_000 + seq)
            code = fake.lexify("????", letters="ABCDEFGHKLMNOPRSTUVX").capitalize()
            records.append({"library_code": code, **_library(fake, code)})
        return _envelope("libraries", sigel, records, data_type="libraries")

    return _load_fixture("library_self", sigel) or _envelope(
        "libraries", sigel, [], data_type="libraries"
    )



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=9001)
