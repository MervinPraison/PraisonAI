"""Shared authorisation + bind guard for the ``launch()`` serving paths.

Both ``Agent.launch()`` (``agent/execution_mixin.py``) and
``PraisonAIAgents.launch()`` (``agents/agents.py``) expose a prompt-execution
HTTP endpoint. They must enforce identical request authorisation and must not
silently bind all interfaces without a token. Factoring the two helpers here
keeps that policy in one place so the two launch paths cannot drift apart.

Stdlib only — no heavy imports, no new public params.
"""

from __future__ import annotations

import os
import secrets as _secrets
from typing import Optional

__all__ = [
    "launch_auth_token",
    "authorise_launch_request",
    "resolve_launch_host",
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


def authorise_launch_request(request) -> bool:
    """Return True if the request carries the configured bearer token.

    When no token is configured this returns True (local-dev flow preserved).
    Accepts either ``Authorization: Bearer <token>`` or ``X-Auth-Token``.
    """
    token = launch_auth_token()
    if not token:
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and _secrets.compare_digest(auth[7:], token):
        return True
    supplied = request.headers.get("X-Auth-Token", "")
    return bool(supplied) and _secrets.compare_digest(supplied, token)


def _is_loopback(host: str) -> bool:
    return host in _LOOPBACK_HOSTS


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
    if launch_auth_token() or _is_loopback(host):
        return host

    global _GENERATED_TOKEN
    if _GENERATED_TOKEN is None:
        _GENERATED_TOKEN = _secrets.token_urlsafe(32)
        print(
            f"🔐 launch() bound to non-loopback host {host!r} without "
            f"PRAISONAI_LAUNCH_AUTH_TOKEN set. Generated a one-time bearer token "
            f"(set PRAISONAI_LAUNCH_AUTH_TOKEN to override): {_GENERATED_TOKEN}"
        )
    os.environ["PRAISONAI_LAUNCH_AUTH_TOKEN"] = _GENERATED_TOKEN
    return host
