import json
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException

FIXTURES = Path(__file__).parents[3] / "tests/fixtures/libris"
app = FastAPI(title="Fake Libris ILL API")


def _load(name: str) -> dict:
    path = FIXTURES / f"{name}.json"
    if not path.exists():
        # Real Libris returns an empty envelope, never a 404, for a view with
        # no records — including for an unknown sigel. Mimic that exactly.
        return {"data_source": "illse", "data_type": "ill_requests",
                "result_type": name, "count": 0, "ill_requests": []}
    return json.loads(path.read_text(encoding="utf-8"))

@app.get("/health")
async def health() -> dict[str, object]:
    fixtures = sorted(p.stem for p in FIXTURES.glob("*.json"))
    return {"status": "ok", "fixtures": len(fixtures), "fixture_dir": str(FIXTURES)}

@app.get("/librisfjarrlan/api/illrequests/{sigel}/{view}")
async def ill_requests(sigel: str, view: str, api_key: str = Header(alias="api-key")):
    if not api_key:
        raise HTTPException(401, "missing api-key header")
    prefix = "lending" if view in {"incoming", "recent", "reservations",
                                   "cancellations"} else "borrowing"
    return _load(f"{prefix}_{view}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=9001)
