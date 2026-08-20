"""Shared URL safety checks for tool HTTP requests (SSRF mitigation)."""

from __future__ import annotations

import ipaddress
import os
import socket
import urllib.parse
from typing import FrozenSet, Optional, Set


def _env_allowlist() -> Set[str]:
    raw = os.environ.get("SEARXNG_URL_ALLOWLIST", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def is_safe_http_url(
    url: str,
    *,
    allow_local: Optional[bool] = None,
    allowlist: FrozenSet[str] = frozenset(),
) -> bool:
    """Return True when *url* is safe for server-side HTTP requests.

    *allowlist* is an explicit per-call-site override. Every resolved address
    is still classified, and an allowlisted hostname only exempts the
    *loopback* class -- private, link-local, multicast and unspecified
    addresses stay blocked even when the host is allowlisted, so an entry can
    never be abused to reach cloud metadata (169.254.169.254) or internal
    ranges.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if allow_local is None:
            allow_local = os.environ.get("ALLOW_LOCAL_CRAWL") == "true"
        if allow_local:
            return True
        is_allowlisted = hostname.lower() in allowlist
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_loopback:
                if is_allowlisted:
                    continue
                return False
            if (
                ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True
    except (socket.gaierror, ValueError, OSError):
        return False


def validate_searxng_url(url: str) -> Optional[str]:
    """Return normalised URL or None if blocked.

    SearXNG is legitimately self-hosted on loopback, so this call site opts
    into the loopback allowlist explicitly (unlike the web crawler).
    """
    if not url:
        return None
    allowlist = frozenset(_env_allowlist() | {"localhost", "127.0.0.1", "::1"})
    if not is_safe_http_url(url, allowlist=allowlist):
        return None
    return url
