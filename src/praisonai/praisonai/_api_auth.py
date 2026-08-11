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
            is in this set, or starts with ``/__praisonai__/``, is allowed
            through without a token.

    Imports of ``hmac``/``starlette`` are kept inside this function so callers
    stay lazy-import friendly.
    """
    import hmac
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.responses import JSONResponse

    public = set(public_paths or ())

    class _APIKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            path = request.url.path
            if path in public or path.startswith("/__praisonai__/"):
                return await call_next(request)
            auth = request.headers.get("Authorization", "")
            header_key = request.headers.get("X-API-Key", "")
            token = auth[7:] if auth.startswith("Bearer ") else header_key
            if not token or not hmac.compare_digest(token, api_key):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            return await call_next(request)

    return _APIKeyMiddleware
