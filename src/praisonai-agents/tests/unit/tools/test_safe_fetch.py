"""Outbound fetches resolve once, pin the address, and re-check every hop.

No test here reaches the network: DNS is stubbed, and the only sockets opened
go to throwaway HTTP servers on 127.0.0.1 or are intercepted before connect.
"""
from __future__ import annotations

import functools
import http.server
import socket
import threading

import pytest

pytest.importorskip("httpx")

from praisonaiagents.tools import url_safety  # noqa: E402

PUBLIC = "93.184.216.34"
CANARY = b"INTERNAL-ONLY-CANARY"


@pytest.fixture(autouse=True)
def _no_opt_outs(monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    monkeypatch.delenv("SEARXNG_URL_ALLOWLIST", raising=False)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)


def _serve(handler_body):
    """Start a loopback server; ``handler_body(handler)`` writes the reply."""
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            handler_body(self)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def stop():
        server.shutdown()
        server.server_close()
        thread.join()

    return server.server_port, hits, stop


def _canary(handler):
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html")
    handler.send_header("Content-Length", str(len(CANARY)))
    handler.end_headers()
    handler.wfile.write(CANARY)


def _answer(ip, port=None, *rest):
    """A getaddrinfo reply for ``ip`` that keeps the caller's port."""
    port = int(port) if port not in (None, "") else 0
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]


def _rebinding_resolver(monkeypatch, host, public_lookups):
    """``host`` answers PUBLIC for the first lookups, then loopback."""
    real = socket.getaddrinfo
    calls = []

    def resolve(name, *args, **kwargs):
        if name == host:
            calls.append(name)
            ip = PUBLIC if len(calls) <= public_lookups else "127.0.0.1"
            return _answer(ip, *args)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    return calls


# --- address classification -------------------------------------------------

@pytest.mark.parametrize(
    "literal",
    [
        "[::ffff:127.0.0.1]",  # IPv4-mapped loopback
        "[::ffff:169.254.169.254]",  # IPv4-mapped metadata
        "[64:ff9b::7f00:1]",  # NAT64 wrapping 127.0.0.1
        "[64:ff9b::a9fe:a9fe]",  # NAT64 wrapping 169.254.169.254
        "[2002:7f00:1::]",  # 6to4 wrapping 127.0.0.1
        "[2002:a9fe:a9fe::]",  # 6to4 wrapping 169.254.169.254
        "[::7f00:1]",  # IPv4-compatible 127.0.0.1
        "[fd00:ec2::254]",  # AWS IPv6 metadata (ULA)
        "100.100.100.200",  # Alibaba metadata (shared space)
    ],
)
def test_ipv6_wrappers_of_internal_ipv4_are_blocked(literal):
    assert url_safety.is_safe_http_url(f"http://{literal}/") is False


def test_backslash_authority_is_rejected():
    # urlparse reads host 1.1.1.1; some clients dial 127.0.0.1.
    assert url_safety.is_safe_http_url("http://127.0.0.1:6666\\@1.1.1.1/") is False


def test_public_literal_still_allowed():
    assert url_safety.is_safe_http_url("http://1.1.1.1/") is True
    assert url_safety.is_safe_http_url("http://[2606:4700:4700::1111]/") is True


# --- safe_fetch -------------------------------------------------------------

def test_safe_fetch_resolves_once_and_dials_the_checked_address(monkeypatch):
    calls = _rebinding_resolver(monkeypatch, "rebind.test", public_lookups=1)
    dialed = []

    def fake_connect(address, *args, **kwargs):
        dialed.append(address[0])
        raise ConnectionRefusedError("intercepted")

    monkeypatch.setattr(socket, "create_connection", fake_connect)

    with pytest.raises(Exception):
        url_safety.safe_fetch("http://rebind.test:8080/")

    assert calls == ["rebind.test"]
    assert dialed == [PUBLIC]


def test_safe_fetch_rejects_internal_and_non_http():
    for url in ("http://127.0.0.1/", "http://169.254.169.254/", "file:///etc/passwd", "ftp://example.com/"):
        with pytest.raises(url_safety.UnsafeURLError):
            url_safety.safe_fetch(url)


def test_safe_fetch_rechecks_every_redirect_hop(monkeypatch):
    internal_port, internal_hits, stop_internal = _serve(_canary)

    def redirect(handler):
        handler.send_response(302)
        handler.send_header("Location", f"http://127.0.0.1:{internal_port}/meta")
        handler.end_headers()

    port, _, stop = _serve(redirect)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: _answer("127.0.0.1", *a))
    try:
        with pytest.raises(url_safety.UnsafeURLError):
            # Only "localhost" is exempted; the redirect names another host.
            url_safety.safe_fetch(f"http://localhost:{port}/", allowlist=frozenset({"localhost"}))
    finally:
        stop()
        stop_internal()
    assert internal_hits == []


def test_safe_fetch_follows_allowed_redirects_and_reports_final_url(monkeypatch):
    def reply(handler):
        if handler.path == "/start":
            handler.send_response(302)
            handler.send_header("Location", "/page")
            handler.end_headers()
        else:
            _canary(handler)

    port, hits, stop = _serve(reply)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: _answer("127.0.0.1", *a))
    try:
        resp = url_safety.safe_fetch(f"http://localhost:{port}/start", allowlist=frozenset({"localhost"}))
    finally:
        stop()
    assert resp.content == CANARY
    assert hits == ["/start", "/page"]
    assert str(resp.url) == f"http://localhost:{port}/page"


def test_allow_local_env_is_the_documented_escape_hatch(monkeypatch):
    port, hits, stop = _serve(_canary)
    monkeypatch.setenv("ALLOW_LOCAL_CRAWL", "true")
    try:
        assert url_safety.safe_fetch(f"http://127.0.0.1:{port}/").content == CANARY
    finally:
        stop()


# --- tools route through the helper -----------------------------------------

def test_spider_scrape_cannot_be_rebound_to_loopback(monkeypatch):
    pytest.importorskip("bs4")
    pytest.importorskip("lxml")
    from praisonaiagents.tools.spider_tools import SpiderTools

    port, hits, stop = _serve(_canary)
    _rebinding_resolver(monkeypatch, "rebind.test", public_lookups=2)
    try:
        result = SpiderTools().scrape_page(f"http://rebind.test:{port}/", timeout=2)
    finally:
        stop()
    assert hits == []
    assert "INTERNAL-ONLY-CANARY" not in str(result)


def test_web_crawl_cannot_be_rebound_to_loopback(monkeypatch):
    from praisonaiagents.tools import web_crawl_tools as w

    port, hits, stop = _serve(_canary)
    _rebinding_resolver(monkeypatch, "rebind.test", public_lookups=1)
    try:
        result = w._crawl_with_httpx([f"http://rebind.test:{port}/"])[0]
    finally:
        stop()
    assert hits == []
    assert "INTERNAL-ONLY-CANARY" not in result["content"]


@pytest.mark.parametrize("entry", ["searxng_tools", "web_search"])
def test_searxng_does_not_follow_redirect_to_internal_host(monkeypatch, entry):
    pytest.importorskip("requests")
    internal_port, internal_hits, stop_internal = _serve(_canary)

    def redirect(handler):
        handler.send_response(302)
        handler.send_header("Location", f"http://metadata.test:{internal_port}/meta")
        handler.end_headers()

    port, _, stop = _serve(redirect)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: _answer("127.0.0.1", *a))
    url = f"http://localhost:{port}/search"
    try:
        if entry == "searxng_tools":
            from praisonaiagents.tools.searxng_tools import searxng_search
            searxng_search("q", searxng_url=url)
        else:
            from praisonaiagents.tools.web_search import _search_searxng
            with pytest.raises(Exception):
                _search_searxng("q", searxng_url=url)
    finally:
        stop()
        stop_internal()
    assert internal_hits == []


def test_web_crawl_redirect_to_internal_is_blocked(monkeypatch):
    """Was a urllib-fallback test; the crawler now has one path, the helper."""
    from praisonaiagents.tools import web_crawl_tools as w

    internal_port, internal_hits, stop_internal = _serve(_canary)

    def redirect(handler):
        handler.send_response(302)
        handler.send_header("Location", f"http://127.0.0.1:{internal_port}/meta")
        handler.end_headers()

    port, _, stop = _serve(redirect)
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: _answer("127.0.0.1", *a))
    monkeypatch.setattr(
        url_safety, "safe_stream",
        functools.partial(url_safety.safe_stream, allowlist=frozenset({"localhost"})),
    )
    try:
        result = w._crawl_with_httpx([f"http://localhost:{port}/"])[0]
    finally:
        stop()
        stop_internal()
    assert internal_hits == []
    assert result["content"] == ""
    assert "blocked" in result["error"].lower()


def test_is_blocked_ip_is_the_public_name_other_packages_import():
    import ipaddress
    from praisonaiagents.tools import url_safety

    assert url_safety._ip_blocked is url_safety.is_blocked_ip
    assert url_safety.is_blocked_ip(ipaddress.ip_address("::ffff:10.0.0.1"))
    assert url_safety.is_blocked_ip(ipaddress.ip_address("127.0.0.1"))
    assert not url_safety.is_blocked_ip(ipaddress.ip_address("127.0.0.1"), loopback_ok=True)
    assert not url_safety.is_blocked_ip(ipaddress.ip_address("8.8.8.8"))
