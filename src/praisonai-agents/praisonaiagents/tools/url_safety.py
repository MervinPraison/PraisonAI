"""Shared URL safety checks for tool HTTP requests (SSRF mitigation)."""

from __future__ import annotations

import ipaddress
import os
import socket
import urllib.parse
from typing import Optional, Set


def _allowlist_hosts() -> Set[str]:
    raw = os.environ.get("SEARXNG_URL_ALLOWLIST", "")
    hosts = {h.strip().lower() for h in raw.split(",") if h.strip()}
    hosts.update({"localhost", "127.0.0.1", "::1"})
    return hosts


def is_safe_http_url(url: str, *, allow_local: Optional[bool] = None) -> bool:
    """Return True when *url* is safe for server-side HTTP requests."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname.lower() in _allowlist_hosts():
            return True
        if allow_local is None:
            allow_local = os.environ.get("ALLOW_LOCAL_CRAWL") == "true"
        if allow_local:
            return True
        for info in socket.getaddrinfo(hostname, None):
            ip = ipaddress.ip_address(info[4][0])
            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        return True
    except (socket.gaierror, ValueError, OSError):
        return False


def validate_searxng_url(url: str) -> Optional[str]:
    """Return normalised URL or None if blocked."""
    if not url:
        return None
    if not is_safe_http_url(url):
        return None
    return url
