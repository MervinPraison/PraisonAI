"""Remote instruction sources and image downloads cannot reach a loopback service.

The stub resolver answers a public address for the first ``public_lookups``
queries of ``rebind.test`` and 127.0.0.1 after that. A loopback HTTP server
plays the internal service. The fix routes both fetches through
``praisonaiagents.tools.url_safety`` (resolve once, pin, re-check redirects).
No test reaches the network: no stub ever answers a public address at the
moment a connection is made.
"""
from __future__ import annotations

import http.server
import socket
import threading

import pytest

PUBLIC = "93.184.216.34"
CANARY = b"INTERNAL-ONLY-CANARY"


@pytest.fixture(autouse=True)
def _no_opt_outs(monkeypatch):
    for name in ("ALLOW_LOCAL_CRAWL", "PRAISONAI_INSTRUCTIONS_ALLOW_LOCAL_URLS",
                 "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def internal():
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Length", str(len(CANARY)))
            self.end_headers()
            self.wfile.write(CANARY)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port, hits
    server.shutdown()
    server.server_close()
    thread.join()


def _rebind(monkeypatch, public_lookups):
    real = socket.getaddrinfo
    calls = []

    def resolve(name, port=None, *args, **kwargs):
        if name != "rebind.test":
            return real(name, port, *args, **kwargs)
        calls.append(name)
        ip = PUBLIC if len(calls) <= public_lookups else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, int(port or 0)))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def test_instruction_source_rebind_is_refused(monkeypatch, internal):
    from praisonai_code.integration import context_files as ctx

    port, hits = internal
    _rebind(monkeypatch, public_lookups=1)
    assert ctx._fetch_remote_source(f"http://rebind.test:{port}/rules.md") is None
    assert hits == []


def test_instruction_source_uses_shared_helper(monkeypatch):
    """The fetch goes through url_safety, not a private opener."""
    from praisonai_code.integration import context_files as ctx
    from praisonaiagents.tools import url_safety

    seen = []

    def fake_stream(url, **kwargs):
        seen.append((url, kwargs.get("allow_local")))
        raise url_safety.UnsafeURLError("stop")

    monkeypatch.setattr(url_safety, "safe_stream", fake_stream)
    monkeypatch.setattr(ctx, "_url_is_fetchable", lambda url: True)
    assert ctx._fetch_remote_source("https://example.com/rules.md") is None
    assert seen == [("https://example.com/rules.md", False)]


def test_image_save_refuses_internal_url(monkeypatch, internal, tmp_path):
    from praisonai_code.cli.features.image import ImageGenerateHandler

    port, hits = internal
    _rebind(monkeypatch, public_lookups=0)
    out = tmp_path / "img.png"
    handler = ImageGenerateHandler.__new__(ImageGenerateHandler)
    ok = handler._save_image({"data": [{"url": f"http://rebind.test:{port}/img.png"}]}, str(out))
    assert ok is False
    assert hits == []
    assert not out.exists()
