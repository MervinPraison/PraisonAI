"""
MCP OAuth Metadata Discovery.

Implements the discovery half of zero-config OAuth for remote MCP servers:

- Parse a ``WWW-Authenticate: Bearer resource_metadata="..."`` challenge from a
  ``401`` response (RFC 9728 / MCP authorization spec).
- Fetch protected-resource metadata (``/.well-known/oauth-protected-resource``).
- Fetch authorization-server metadata
  (``/.well-known/oauth-authorization-server`` with an OpenID configuration
  fallback), yielding ``authorization_endpoint``, ``token_endpoint`` and
  ``registration_endpoint``.

Network access is HTTPS-only (except loopback) to preserve the SSRF-safe
posture used elsewhere in the MCP transports. ``requests`` is imported lazily so
this module stays additive and does not affect import time.
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from praisonaiagents._logging import get_logger

logger = get_logger("mcp-oauth-discovery")

_LOCALHOST_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _require_https(url: str) -> None:
    """Reject non-HTTPS metadata URLs (loopback HTTP is allowed for testing)."""
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and (parsed.hostname or "") in _LOCALHOST_HOSTS:
        return
    raise ValueError(
        f"Refusing to fetch OAuth metadata over insecure transport: {url!r}"
    )


def parse_www_authenticate(header: Optional[str]) -> Dict[str, str]:
    """
    Parse a ``WWW-Authenticate`` challenge header into its parameters.

    Only ``Bearer`` challenges are relevant here. Returns a dict of the
    ``key="value"`` auth-params (e.g. ``resource_metadata``, ``scope``,
    ``error``). Returns an empty dict when the header is missing or not a
    Bearer challenge.
    """
    if not header:
        return {}

    # Strip the leading scheme (e.g. "Bearer ") if present.
    stripped = header.strip()
    if stripped.lower().startswith("bearer"):
        stripped = stripped[len("bearer"):].lstrip()

    params: Dict[str, str] = {}
    for match in re.finditer(r'(\w+)\s*=\s*"([^"]*)"', stripped):
        params[match.group(1).lower()] = match.group(2)
    return params


def _get_json(url: str, timeout: float = 10.0) -> Dict[str, Any]:
    """Fetch and parse a JSON metadata document over HTTPS.

    Redirects are followed but every hop — including the final destination — is
    re-validated with :func:`_require_https` so a redirect cannot escape the
    HTTPS/loopback guard to an internal or plaintext endpoint (SSRF-safe).
    """
    _require_https(url)
    import requests  # lazy import — optional dependency

    resp = requests.get(
        url,
        headers={"Accept": "application/json"},
        timeout=timeout,
        allow_redirects=True,
    )
    # Re-validate every redirect hop and the final URL: allow_redirects only
    # checks the initial URL, so a 30x to http:// or an internal host would
    # otherwise bypass the guard.
    for previous in getattr(resp, "history", None) or []:
        _require_https(previous.url)
    _require_https(resp.url)
    resp.raise_for_status()
    return resp.json()


def _wellknown_candidates(server_url: str) -> List[str]:
    """Build ``.well-known`` metadata URL candidates for a server URL."""
    parsed = urlparse(server_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    return [
        urljoin(origin + "/", ".well-known/oauth-protected-resource"),
        urljoin(origin + "/", ".well-known/oauth-authorization-server"),
        urljoin(origin + "/", ".well-known/openid-configuration"),
    ]


def discover_protected_resource(
    server_url: str,
    resource_metadata_url: Optional[str] = None,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """
    Discover protected-resource metadata for an MCP server.

    Args:
        server_url: The MCP server URL that returned a 401.
        resource_metadata_url: Optional explicit URL from the
            ``WWW-Authenticate: resource_metadata="..."`` challenge.
        timeout: Per-request timeout in seconds.

    Returns:
        The protected-resource metadata document, or None if unavailable.
    """
    url = resource_metadata_url or _wellknown_candidates(server_url)[0]
    try:
        return _get_json(url, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - discovery is best-effort
        logger.debug(f"Protected-resource metadata unavailable at {url}: {exc}")
        return None


def discover_authorization_server(
    server_url: str,
    authorization_servers: Optional[List[str]] = None,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """
    Discover authorization-server metadata.

    Tries, in order: any ``authorization_servers`` advertised by the
    protected-resource metadata, then the server-origin
    ``/.well-known/oauth-authorization-server`` and OpenID-configuration
    fallbacks.

    Returns the first metadata document that exposes at least an
    ``authorization_endpoint`` and ``token_endpoint``, or None.
    """
    candidates: List[str] = []

    for issuer in authorization_servers or []:
        issuer = issuer.rstrip("/")
        candidates.append(issuer + "/.well-known/oauth-authorization-server")
        candidates.append(issuer + "/.well-known/openid-configuration")

    # Fall back to the resource server's own origin.
    for candidate in _wellknown_candidates(server_url)[1:]:
        candidates.append(candidate)

    for url in candidates:
        try:
            metadata = _get_json(url, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - best-effort discovery
            logger.debug(f"Auth-server metadata unavailable at {url}: {exc}")
            continue
        if metadata.get("authorization_endpoint") and metadata.get("token_endpoint"):
            return metadata

    return None


def discover_oauth_metadata(
    server_url: str,
    www_authenticate: Optional[str] = None,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """
    Full metadata discovery for an OAuth-protected MCP server.

    Combines the ``WWW-Authenticate`` challenge (if any), protected-resource
    metadata, and authorization-server metadata into a single normalised dict:

        {
            "authorization_endpoint": str,
            "token_endpoint": str,
            "registration_endpoint": str | None,
            "scopes_supported": list[str] | None,
            "resource": str | None,
        }

    Returns None if a usable authorization/token endpoint pair cannot be found.
    """
    challenge = parse_www_authenticate(www_authenticate)

    resource_meta = discover_protected_resource(
        server_url,
        resource_metadata_url=challenge.get("resource_metadata"),
        timeout=timeout,
    )

    authorization_servers = None
    resource_id = None
    if resource_meta:
        authorization_servers = resource_meta.get("authorization_servers")
        resource_id = resource_meta.get("resource")

    auth_meta = discover_authorization_server(
        server_url,
        authorization_servers=authorization_servers,
        timeout=timeout,
    )
    if not auth_meta:
        return None

    # Enforce the HTTPS/loopback guard on the advertised endpoints too: an
    # HTTPS metadata document must not be able to smuggle a plaintext
    # authorization/token/registration endpoint that would later receive
    # authorization codes, PKCE verifiers, refresh tokens, or client secrets
    # over an insecure transport.
    authorization_endpoint = auth_meta["authorization_endpoint"]
    token_endpoint = auth_meta["token_endpoint"]
    registration_endpoint = auth_meta.get("registration_endpoint")
    _require_https(authorization_endpoint)
    _require_https(token_endpoint)
    if registration_endpoint:
        _require_https(registration_endpoint)

    return {
        "authorization_endpoint": authorization_endpoint,
        "token_endpoint": token_endpoint,
        "registration_endpoint": registration_endpoint,
        "scopes_supported": (
            auth_meta.get("scopes_supported")
            or (resource_meta or {}).get("scopes_supported")
        ),
        "resource": resource_id,
    }
