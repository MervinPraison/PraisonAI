"""Shared API-key authentication middleware for PraisonAI HTTP servers.

Consolidates the bearer / ``X-API-Key`` token extraction and constant-time
comparison used by both the ``serve`` feature and the async jobs server so a
future auth fix only needs to be made in one place.
"""

from typing import Any, Iterable, Optional


def build_api_key_middleware(api_key: str, public_paths: Optional[Iterable[str]] = None) -> Any:
    """Return a configured ``BaseHTTPMiddleware`` subclass enforcing ``api_key``.

    Args:
        api_key: The expected API key; requests must present it via a
            ``Bearer`` ``Authorization`` header or ``X-API-Key`` header.
        public_paths: Paths that bypass authentication. Any request whose path
            is in this set, or is exactly ``/__praisonai__/discovery`` (the
            unauthenticated capability document), is allowed through without a
            token. The discovery path is matched exactly -- never by prefix --
            so a server whose ``api_prefix`` happens to sit under
            ``/__praisonai__`` does not silently expose its routes.

    Imports of ``hmac``/``starlette`` are kept inside this function so callers
    stay lazy-import friendly.
    """
    import hmac
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    public = set(public_paths or ())
    public.add("/__praisonai__/discovery")

    class _APIKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            path = request.url.path
            if path in public:
                return await call_next(request)
            auth = request.headers.get("Authorization", "")
            header_key = request.headers.get("X-API-Key", "")
            token = auth[7:] if auth.startswith("Bearer ") else header_key
            if not token or not hmac.compare_digest(token, api_key):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await call_next(request)

    return _APIKeyMiddleware


def guard_browser_app(app: Any, host: str, token: Optional[str], *, server: str, token_env: str) -> Any:
    """The shared bind rule for a browser-facing server (dashboard, Replay).

    Loopback binds run keyless and answer only same-site, loopback-named
    requests. Any other bind needs ``token`` (else ``ValueError``), and every
    request must carry it: ``?token=`` once (then a cookie) or a Bearer header
    when PraisonAI UI is installed, a Bearer/``X-API-Key`` header otherwise.
    """
    from praisonaiagents.agent.launch_security import require_bind_token
    from praisonaiagents.agent.origin_guard import guard_loopback_requests

    token = require_bind_token(host, token, server=server, hint=f"Set {token_env}")
    if token:
        try:
            from praisonaiui.auth import TokenQueryMiddleware
        except ImportError:
            app = build_api_key_middleware(token, {"/health"})(app)
        else:
            app = TokenQueryMiddleware(app, expected_token=token)
    return guard_loopback_requests(app, host)
