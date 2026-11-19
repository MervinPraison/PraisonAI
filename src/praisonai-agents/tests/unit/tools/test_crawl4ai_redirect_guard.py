"""crawl4ai crawls cannot be steered to an internal URL after the seed check.

The seed URL is checked once; the browser then follows HTTP redirects,
meta-refresh and script navigations and loads subresources on its own. The
fix routes every browser request through the SSRF check (``page.route``) and
refuses a result whose final URL fails it (the route does not see HTTP 3xx hops).

The browser tests use one loopback server. The SSRF check is replaced by one
that treats any path containing ``secret`` as internal, so the seed passes
and the target does not; no DNS or outside network is involved.
"""
from __future__ import annotations

import asyncio
import functools
import http.server
import os
import threading
import types

import pytest

CANARY = "INTERNAL-ONLY-CANARY"


def _fake_url_check(url: str) -> bool:
    return "secret" not in url


# --- unit level (no browser) ---------------------------------------------


def test_final_url_check_marks_result_failed(monkeypatch):
    from praisonaiagents.tools import crawl4ai_tools

    monkeypatch.setattr(crawl4ai_tools, "_is_safe_crawl_url", _fake_url_check)
    blocked = types.SimpleNamespace(success=True, error_message=None,
                                    redirected_url="http://127.0.0.1:1/secret")
    fine = types.SimpleNamespace(success=True, error_message=None,
                                 redirected_url="http://127.0.0.1:1/page")
    assert crawl4ai_tools._refuse_blocked_final(blocked).success is False
    assert "SSRF" in blocked.error_message
    assert crawl4ai_tools._refuse_blocked_final(fine).success is True


def test_route_guard_aborts_unsafe_requests(monkeypatch):
    from praisonaiagents.tools import crawl4ai_tools

    monkeypatch.setattr(crawl4ai_tools, "_is_safe_crawl_url", _fake_url_check)
    calls = []

    class Route:
        def __init__(self, url):
            self.request = types.SimpleNamespace(url=url)

        async def abort(self):
            calls.append(("abort", self.request.url))

        async def fallback(self):
            calls.append(("fallback", self.request.url))

    for url in ("http://127.0.0.1:1/secret", "http://127.0.0.1:1/ok", "data:text/plain,x"):
        asyncio.run(crawl4ai_tools._route_guard(Route(url)))
    assert calls == [("abort", "http://127.0.0.1:1/secret"),
                     ("fallback", "http://127.0.0.1:1/ok"),
                     ("fallback", "data:text/plain,x")]


def test_crawlers_get_the_guard_hook():
    from praisonaiagents.tools import crawl4ai_tools

    hooks = {}
    crawler = types.SimpleNamespace(crawler_strategy=types.SimpleNamespace(
        set_hook=lambda name, fn: hooks.update({name: fn})))
    assert crawl4ai_tools._guard_crawler(crawler) is crawler
    assert hooks == {"on_page_context_created": crawl4ai_tools._guard_page}


# --- real browser (opt-in extra installed) --------------------------------


@functools.lru_cache(maxsize=None)
def _browser_available() -> bool:
    """crawl4ai is installed and Playwright's Chromium is present (skip otherwise)."""
    try:
        from praisonaiagents.tools.crawl4ai_tools import _check_crawl4ai_available
        if not _check_crawl4ai_available()[0]:
            return False
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:  # noqa: BLE001 - any failure means "skip"
        return False


@pytest.fixture
def site():
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            if self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", "/secret")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path == "/meta":
                body = ('<html><head><meta http-equiv="refresh" content="0;url=/secret">'
                        "</head><body>moving on</body></html>").encode()
            else:
                body = f"<html><body><p>{CANARY} {CANARY} {CANARY}</p></body></html>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", hits
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.skipif(not _browser_available(), reason="crawl4ai + Playwright Chromium not installed")
@pytest.mark.parametrize("path", ["/redirect", "/meta"])
def test_web_crawl_crawl4ai_does_not_return_internal_content(monkeypatch, site, path):
    from praisonaiagents.tools import crawl4ai_tools, web_crawl_tools

    base, hits = site
    monkeypatch.setattr(crawl4ai_tools, "_is_safe_crawl_url", _fake_url_check)
    monkeypatch.setattr(web_crawl_tools, "_is_safe_crawl_url", _fake_url_check)
    [result] = web_crawl_tools._crawl_with_crawl4ai([base + path])
    assert CANARY not in repr(result)
    if path == "/meta":
        # A browser navigation is stopped before it is sent.
        assert "/secret" not in hits


@pytest.mark.skipif(not _browser_available(), reason="crawl4ai + Playwright Chromium not installed")
def test_crawl4ai_tools_crawl_does_not_return_internal_content(monkeypatch, site):
    from praisonaiagents.tools import crawl4ai_tools

    base, _hits = site
    monkeypatch.setattr(crawl4ai_tools, "_is_safe_crawl_url", _fake_url_check)

    async def run():
        tools = crawl4ai_tools.Crawl4AITools()
        try:
            return await tools.crawl(base + "/redirect")
        finally:
            await tools.close()

    result = asyncio.run(run())
    assert CANARY not in repr(result)
    assert result["success"] is False


@pytest.mark.skipif(not _browser_available(), reason="crawl4ai + Playwright Chromium not installed")
def test_control_safe_page_is_still_crawled(monkeypatch, site):
    """Control: the guard does not break normal crawls (and the browser runs)."""
    from praisonaiagents.tools import crawl4ai_tools, web_crawl_tools

    base, _hits = site
    monkeypatch.setattr(crawl4ai_tools, "_is_safe_crawl_url", _fake_url_check)
    monkeypatch.setattr(web_crawl_tools, "_is_safe_crawl_url", _fake_url_check)
    [result] = web_crawl_tools._crawl_with_crawl4ai([base + "/page"])
    assert CANARY in repr(result)
