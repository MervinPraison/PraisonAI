"""
MCP OAuth Dynamic Client Registration (RFC 7591).

Performs an anonymous dynamic client registration against an authorization
server's ``registration_endpoint`` so that connecting to a hosted MCP server by
URL requires no pre-provisioned ``client_id``. The registered client info is
returned for persistence via :meth:`MCPAuthStorage.set_client_info`.

``requests`` is imported lazily to keep this module additive.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from praisonaiagents._logging import get_logger

logger = get_logger("mcp-oauth-registration")

_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _require_https(url: str) -> None:
    """Reject non-HTTPS registration URLs (loopback HTTP allowed for testing)."""
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and (parsed.hostname or "") in _LOCALHOST_HOSTS:
        return
    raise ValueError(
        f"Refusing to register client over insecure transport: {url!r}"
    )


def register_client(
    registration_endpoint: str,
    redirect_uris: List[str],
    client_name: str = "PraisonAI Agent",
    scope: Optional[str] = None,
    timeout: float = 10.0,
) -> Dict[str, Any]:
    """
    Register a public OAuth client via RFC 7591 Dynamic Client Registration.

    Args:
        registration_endpoint: The ``registration_endpoint`` from auth-server
            metadata.
        redirect_uris: Allowed redirect URIs (the loopback callback URL).
        client_name: Human-readable client name.
        scope: Optional space-delimited scope string to request.
        timeout: Request timeout in seconds.

    Returns:
        The registration response containing at least ``client_id`` (and
        ``client_secret`` for confidential clients).

    Raises:
        ValueError: If the endpoint is insecure or the response lacks a
            ``client_id``.
    """
    _require_https(registration_endpoint)
    import requests  # lazy import — optional dependency

    payload: Dict[str, Any] = {
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    if scope:
        payload["scope"] = scope

    resp = requests.post(
        registration_endpoint,
        json=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    client_info = resp.json()

    if not client_info.get("client_id"):
        raise ValueError(
            "Dynamic client registration response missing 'client_id'"
        )

    logger.debug(
        f"Registered OAuth client '{client_info.get('client_id')}' "
        f"at {registration_endpoint}"
    )
    return client_info
