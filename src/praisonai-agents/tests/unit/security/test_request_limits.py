"""Shared request limits: bounded per-key state and a request body cap."""

import asyncio

from praisonaiagents.agent.request_limits import BoundedDict, limit_request_body


def test_bounded_dict_evicts_oldest_and_refreshes_on_write():
    d = BoundedDict(3)
    for k in "abc":
        d[k] = k
    d["a"] = "a2"  # rewrite moves "a" to newest
    d["d"] = "d"
    assert list(d) == ["c", "a", "d"]
    assert len(d) == 3


def _run(app, headers, chunks):
    sent = []
    queue = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1}
             for i, c in enumerate(chunks)]

    async def receive():
        return queue.pop(0) if queue else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "headers": headers}
    asyncio.run(app(scope, receive, send))
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


async def _echo_app(scope, receive, send):
    body = b""
    while True:
        msg = await receive()
        body += msg.get("body", b"")
        if not msg.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": body})


def test_declared_oversize_body_is_refused_before_reading():
    app = limit_request_body(_echo_app, max_bytes=10)
    assert _run(app, [(b"content-length", b"11")], [b"x" * 11]) == 413
    assert _run(app, [(b"content-length", b"bogus")], [b""]) == 400


def test_streamed_oversize_body_is_refused():
    app = limit_request_body(_echo_app, max_bytes=10)
    assert _run(app, [], [b"x" * 6, b"x" * 6]) == 413


def test_body_within_limit_passes():
    app = limit_request_body(_echo_app, max_bytes=10)
    assert _run(app, [(b"content-length", b"10")], [b"x" * 10]) == 200
