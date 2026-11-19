"""Shared authorisation + bind guard for ``launch()`` and every SDK server.

Both ``Agent.launch()`` (``agent/execution_mixin.py``) and
``PraisonAIAgents.launch()`` (``agents/agents.py``) expose a prompt-execution
HTTP endpoint. They must enforce identical request authorisation and must not
silently bind all interfaces without a token. Factoring the two helpers here
keeps that policy in one place so the two launch paths cannot drift apart.

Stdlib only — no heavy imports, no new public params.
"""

from __future__ import annotations

import hmac
import os
import secrets as _secrets
from typing import Optional

__all__ = [
    "launch_auth_token",
    "token_matches",
    "authorise_launch_request",
    "resolve_launch_host",
    "require_bind_token",
]

# Hosts that are safe to serve keyless on: loopback only.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

# One auto-generated token per process, reused across launches so a later
# non-loopback launch cannot mint a fresh token and lock out an endpoint that
# is already serving with the previously generated one.
_GENERATED_TOKEN: Optional[str] = None


def launch_auth_token() -> Optional[str]:
    """Return the configured launch bearer token, if any."""
    return os.environ.get("PRAISONAI_LAUNCH_AUTH_TOKEN")


def token_matches(supplied: Optional[str], expected: Optional[str]) -> bool:
    """Constant-time token check shared by every SDK server.

    Compares UTF-8 bytes so non-ASCII input cannot raise; a missing or empty
    value on either side never matches.
    """
    if not supplied or not expected:
        return False
    return hmac.compare_digest(str(supplied).encode("utf-8"), str(expected).encode("utf-8"))


def authorise_launch_request(request) -> bool:
    """Return True if the request carries the configured bearer token.

    When no token is configured this returns True (local-dev flow preserved).
    Accepts either ``Authorization: Bearer <token>`` or ``X-Auth-Token``.
    """
    token = launch_auth_token()
    if not token:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and token_matches(auth[7:], token):
        return True
    return token_matches(request.headers.get("X-Auth-Token"), token)


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_HOSTS:
        return True
    import ipaddress

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def require_bind_token(
    host: str,
    token: Optional[str],
    *,
    server: str,
    hint: str,
    generate_into: Optional[str] = None,
) -> Optional[str]:
    """The one bind guard every network server calls before it binds.

    Loopback binds may run keyless. A non-loopback bind needs ``token``; when
    it is missing the guard either raises ``ValueError`` (default) or, if
    ``generate_into`` names an env var, mints the process token, exports it
    there, prints it once and returns it. Returns the token to enforce.
    """
    if token or _is_loopback(host):
        return token
    if generate_into is None:
        raise ValueError(
            f"{server} refuses to bind non-loopback host {host!r} without an "
            f"auth token. {hint}, or bind to 127.0.0.1."
        )
    global _GENERATED_TOKEN
    if _GENERATED_TOKEN is None:
        _GENERATED_TOKEN = _secrets.token_urlsafe(32)
    os.environ[generate_into] = _GENERATED_TOKEN
    print(
        f"🔐 {server} bound to non-loopback host {host!r} without "
        f"{generate_into} set. Generated a one-time bearer token "
        f"(set {generate_into} to override): {_GENERATED_TOKEN}"
    )
    return _GENERATED_TOKEN


def resolve_launch_host(host: str) -> str:
    """Fail-closed bind guard, mirroring the ``serve``/jobs precedent.

    * Token set → bind ``host`` unchanged (auth protects the endpoint).
    * Token unset + loopback host → bind unchanged (local dev unchanged).
    * Token unset + non-loopback host → auto-generate a token, export it via
      ``PRAISONAI_LAUNCH_AUTH_TOKEN`` so every route enforces it, and print it
      once. This closes the unauthenticated-exposure hole without refusing to
      start.

    Returns the host to bind (unchanged; the guard acts on the token, not the
    host, so an explicit ``0.0.0.0`` is still honoured — just never keyless).

    A generated token is reused for the lifetime of the process: repeated
    non-loopback launches share the one token rather than each minting a fresh
    one, so a later launch cannot invalidate an already-running endpoint's
    clients.
    """
    require_bind_token(
        host, launch_auth_token(), server="launch()",
        hint="Set PRAISONAI_LAUNCH_AUTH_TOKEN",
        generate_into="PRAISONAI_LAUNCH_AUTH_TOKEN",
    )
    return host
