"""Read-only probe of the Libris ILL API.

No writes are possible: the transport rejects any non-read method before it
reaches the network. Libris has no undo — this guard is not a formality.
"""

import os
import sys
import httpx2
import asyncio


READ_ONLY_METHODS = {"GET", "HEAD", "OPTIONS"}
BASE = "https://iller.libris.kb.se/librisfjarrlan/api"


class ReadOnlyTransport(httpx2.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        if request.method not in READ_ONLY_METHODS:
            raise RuntimeError(
                f"BLOCKED {request.method} {request.url} — discovery is read-only"
            )
        return await super().handle_async_request(request)


async def probe(client, sigel):
    # /last is the cheapest call that returns a real record.
    r = await client.get(f"/illrequests/{sigel}/last")
    print(f"  GET /illrequests/{sigel}/last")
    print(f"    http status     : {r.status_code}")  # undocumented — observe
    print(f"    content-type    : {r.headers.get('content-type')}")
    print(
        f"    rate-limit hdrs : "
        f"{ {k: v for k, v in r.headers.items() if 'ratelimit' in k.lower()} or 'NONE' }"
    )

    body = r.json()
    print(f"    envelope keys   : {sorted(body.keys())}")
    print(f"    count           : {body.get('count')}")
    print(
        f"    pagination keys : "
        f"{[k for k in body if any(t in k.lower() for t in ('page', 'cursor', 'next', 'offset'))] or 'NONE'}"
    )

    if body.get("ill_requests"):
        rec = body["ill_requests"][0]
        print(f"    lf_number       : {rec.get('lf_number')}")
        print(f"    last_modified   : {rec.get('last_modified')!r}  (store opaque)")
        print(
            f"    status/code     : {rec.get('status')!r} / {rec.get('status_code')!r}"
        )
        print(f"    user (patron)   : {rec.get('user')!r}   <-- Part 1b question")




async def main():
    sigel = os.environ["HALMSTAD_LIBRIS_USERNAME"]
    async with httpx2.AsyncClient(
        transport=ReadOnlyTransport(),
        base_url=BASE,
        headers={"api-key": os.environ["HALMSTAD_LIBRIS_PASSWORD"]},  # header auth, not Bearer
        timeout=httpx2.Timeout(connect=5, read=30, write=10, pool=5),
        follow_redirects=False,
    ) as client:
        print("Libris ILL API:")
        await probe(client, sigel)

        try:  # the guard must fire
            await client.post(f"/illrequests/{sigel}/1", data={"action": "read"})
            sys.exit("FAIL: a write was not blocked")
        except RuntimeError as e:
            print(f"    write guard     : OK ({e})")


asyncio.run(main())
