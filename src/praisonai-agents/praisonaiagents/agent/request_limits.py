"""Request limits shared by the SDK's HTTP servers. Stdlib only.

* ``limit_request_body(app)`` wraps any ASGI app so a request body larger
  than the limit gets ``413`` before it is buffered in memory.
* ``BoundedDict`` is a dict that forgets its oldest entry past a size cap,
  for per-client or per-label state a caller can make arbitrarily many of.
"""

from __future__ import annotations

import os
from collections import OrderedDict

__all__ = ["DEFAULT_MAX_BODY_BYTES", "BoundedDict", "limit_request_body"]

DEFAULT_MAX_BODY_BYTES = int(os.environ.get("PRAISONAI_MAX_BODY_BYTES", 10 * 1024 * 1024))


class BoundedDict(OrderedDict):
    """Insertion-ordered dict that evicts its oldest key past ``max_items``."""

    def __init__(self, max_items: int = 10_000):
        super().__init__()
        self.max_items = max_items

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.max_items:
            self.popitem(last=False)


class _BodyTooLarge(Exception):
    pass


async def _reject(send, status: int = 413) -> None:
    body = b'{"error": "request body too large"}' if status == 413 else b'{"error": "bad request"}'
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


def limit_request_body(app, max_bytes: int | None = None):
    """Return ``app`` wrapped so no request body over ``max_bytes`` is read.

    Checks ``Content-Length`` up front and counts streamed (chunked) bytes.
    """
    limit = DEFAULT_MAX_BODY_BYTES if max_bytes is None else max_bytes

    async def wrapped(scope, receive, send):
        if scope.get("type") != "http":
            return await app(scope, receive, send)
        for name, value in scope.get("headers", []):
            if name.lower() == b"content-length":
                try:
                    if int(value) > limit:
                        return await _reject(send)
                except ValueError:
                    return await _reject(send, 400)
        seen = 0
        started = False

        async def counted_receive():
            nonlocal seen
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _BodyTooLarge
            return message

        async def tracked_send(message):
            nonlocal started
            started = started or message.get("type") == "http.response.start"
            await send(message)

        try:
            await app(scope, counted_receive, tracked_send)
        except _BodyTooLarge:
            if not started:
                await _reject(send)

    return wrapped
