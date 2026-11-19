"""Cross-site request guard for servers bound to loopback. Stdlib only.

A keyless server on 127.0.0.1 is still reachable from a web page in the
user's browser: by a cross-site POST (the page's ``Origin`` is foreign) or
by DNS rebinding (the ``Host`` is the page's own name resolved to
127.0.0.1). ``guard_loopback_requests(app, host)`` refuses both with 403
when ``host`` is a loopback bind; other binds are returned unchanged
(they need a token, see ``launch_security.require_bind_token``). With
``host=None`` (an app factory that does not know its bind) only the
``Origin`` half is checked.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlsplit

from .launch_security import _is_loopback

__all__ = ["guard_loopback_requests", "is_loopback_request"]


def _loopback_name(hostname: str) -> bool:
    hostname = hostname.strip("[]").lower()
    return _is_loopback(hostname) or hostname.endswith(".localhost")


def is_loopback_request(headers: dict, check_host: bool = True) -> bool:
    """True when ``Host`` and any ``Origin`` both name a loopback host."""
    host = headers.get("host", "")
    if check_host and not _loopback_name(urlsplit(f"//{host}").hostname or ""):
        return False
    origin = headers.get("origin")
    if origin is None:
        return True
    return _loopback_name(urlsplit(origin).hostname or "")


def guard_loopback_requests(app, host: Optional[str]):
    """Wrap ASGI ``app`` so a loopback bind serves only loopback-named requests."""
    if host is not None and not _is_loopback(host):
        return app

    async def wrapped(scope, receive, send):
        if scope.get("type") in ("http", "websocket"):
            headers = {k.decode("latin-1").lower(): v.decode("latin-1")
                       for k, v in scope.get("headers", [])}
            if not is_loopback_request(headers, check_host=host is not None):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                    return
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body",
                            "body": b'{"error": "cross-site request refused"}'})
                return
        await app(scope, receive, send)

    return wrapped
