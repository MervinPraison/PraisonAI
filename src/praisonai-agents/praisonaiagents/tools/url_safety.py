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



def is_ambiguous_numeric_host(hostname: str) -> bool:
    """True for dotted numeric hosts whose labels are not plain decimal.

    Different resolvers disagree about these, and the disagreement is the
    vulnerability. glibc's inet_aton reads a leading zero as OCTAL, so
    "0177.0.0.1" is 127.0.0.1 (loopback); getaddrinfo on macOS reads the same
    label as decimal and answers 177.0.0.1, a public address. A validator that
    asks the resolver can therefore clear a host the HTTP client then connects
    to on loopback -- the parser differential behind GHSA-5c6w-wwfq-7qqm.

    Hex labels ("0x7f.0.0.1") are ambiguous the same way. Neither form has a
    legitimate use in a URL, so callers reject them outright instead of trying
    to guess which parser the transport will agree with. Canonical decimal
    dotted-quads and ordinary hostnames are unaffected.
    """
    if not hostname:
        return False
    labels = hostname.lower().rstrip(".").split(".")
    if not (2 <= len(labels) <= 4) or not all(labels):
        return False

    def _numeric(label: str) -> bool:
        return label.isdigit() or (
            label.startswith("0x")
            and len(label) > 2
            and all(c in "0123456789abcdef" for c in label[2:])
        )

    def _ambiguous(label: str) -> bool:
        return label.startswith("0x") or (
            len(label) > 1 and label.startswith("0") and label.isdigit()
        )

    return all(_numeric(l) for l in labels) and any(_ambiguous(l) for l in labels)


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
        # Reject before resolving: getaddrinfo's answer for these is not
        # necessarily the address the HTTP client will connect to.
        if is_ambiguous_numeric_host(hostname):
            return False
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
