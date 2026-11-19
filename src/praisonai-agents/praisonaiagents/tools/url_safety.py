"""Shared URL safety checks for tool HTTP requests (SSRF mitigation)."""

from __future__ import annotations

import contextlib
import ipaddress
import os
import socket
import urllib.parse
from typing import FrozenSet, Optional, Set

from ..errors import PraisonAIError


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
        _pin(url, allowlist, allow_local)
        return True
    except UnsafeURLError:
        return False


class UnsafeURLError(ValueError, PraisonAIError):
    """An outbound URL was refused by the SSRF guard."""


def is_blocked_ip(ip, loopback_ok: bool = False) -> bool:
    """True for a non-global or multicast address, also as IPv4 inside IPv6 (mapped, 6to4, NAT64, compat)."""
    ips = [ip] + [a for a in (getattr(ip, "ipv4_mapped", None), getattr(ip, "sixtofour", None)) if a]
    if ip.version == 6 and (ip in ipaddress.ip_network("64:ff9b::/96") or 1 < int(ip) < 2 ** 32):
        ips.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return any(not (a.is_loopback and loopback_ok) and (not a.is_global or a.is_multicast) for a in ips)


_ip_blocked = is_blocked_ip  # private alias kept for existing callers and tests


def _pin(url: str, allowlist: FrozenSet[str], allow_local: Optional[bool]):
    """Resolve *url* once, check every address, return ``(dial_url, authority, host)``.
    ``dial_url`` names the checked IP so the connection cannot be rebound."""
    try:
        if any(c in url for c in "\\\r\n\t"):
            raise ValueError("backslash or control character")
        parts = urllib.parse.urlsplit(url)
        host, port = parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)
        if parts.scheme not in ("http", "https") or not host or is_ambiguous_numeric_host(host):
            raise ValueError("only http(s) URLs with a plain host")
        ips = [ipaddress.ip_address(i[4][0].split("%")[0])
               for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
    except (OSError, TypeError, ValueError) as exc:
        raise UnsafeURLError(f"URL blocked: {url!r} ({exc})") from None
    if allow_local is None:  # documented local-development opt-out
        allow_local = os.environ.get("ALLOW_LOCAL_CRAWL") == "true"
    if not ips or (not allow_local and any(_ip_blocked(ip, host.lower() in allowlist) for ip in ips)):
        raise UnsafeURLError(f"URL blocked: {host} resolves to a private or internal address")
    dial = f"[{ips[0]}]" if ips[0].version == 6 else str(ips[0])
    target = urllib.parse.urlunsplit((parts.scheme, f"{dial}:{port}", parts.path or "/", parts.query, ""))
    return target, parts.netloc.rpartition("@")[2], host


@contextlib.contextmanager
def safe_stream(url: str, *, method: str = "GET", headers: Optional[dict] = None, allowlist: FrozenSet[str] = frozenset(),
                allow_local: Optional[bool] = None, max_redirects: int = 5, **kwargs):
    """Yield a streamed ``httpx.Response`` for an untrusted *url* (SSRF-safe).

    Every hop is checked by :func:`_pin` and dialled at the checked IP; GET
    redirects are re-checked and drop credentials on a host change.
    ``ALLOW_LOCAL_CRAWL=true`` lifts the address check for local development.
    """
    import httpx

    client_kw = {k: kwargs.pop(k) for k in ("timeout", "verify") if k in kwargs}
    headers = dict(headers or {})
    for _ in range(max_redirects + 1):
        target, authority, host = _pin(url, allowlist, allow_local)
        with httpx.Client(follow_redirects=False, **client_kw) as client:
            request = client.build_request(method, target, headers={**headers, "Host": authority},
                                           extensions={"sni_hostname": host}, **kwargs)
            response = client.send(request, stream=True)
            try:
                location = response.headers.get("location")
                if not (response.is_redirect and location and method in ("GET", "HEAD")):
                    request.url = httpx.URL(url)
                    yield response
                    return
            finally:
                response.close()
        url = urllib.parse.urljoin(url, location)
        if urllib.parse.urlsplit(url).hostname != host:
            headers = {k: v for k, v in headers.items() if k.lower() not in ("authorization", "cookie")}
    raise UnsafeURLError(f"Too many redirects: {url}")


def safe_fetch(url: str, **kwargs):
    """:func:`safe_stream`, returning the fully read ``httpx.Response``."""
    with safe_stream(url, **kwargs) as response:
        response.read()
    return response


def searxng_allowlist() -> FrozenSet[str]:
    return frozenset(_env_allowlist() | {"localhost", "127.0.0.1", "::1"})


def validate_searxng_url(url: str) -> Optional[str]:
    """Return normalised URL or None if blocked.

    SearXNG is legitimately self-hosted on loopback, so this call site opts
    into the loopback allowlist explicitly (unlike the web crawler).
    """
    if not url:
        return None
    if not is_safe_http_url(url, allowlist=searxng_allowlist()):
        return None
    return url
