"""Wrapper URL fetches share the SDK's pinned, re-checked fetch (url_safety).

DNS is stubbed: ``rebind.test`` answers a public address for the first lookups
and 127.0.0.1 afterwards, and a loopback server plays the internal service. A
pinned fetch never reaches it. No test touches the network.
"""
from __future__ import annotations

import http.server
import socket
import threading

import pytest

pytest.importorskip("httpx")

PUBLIC = "93.184.216.34"


@pytest.fixture(autouse=True)
def _no_opt_outs(monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def internal():
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            body = b"<html><body>INTERNAL-ONLY-CANARY</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_port, hits
    server.shutdown()
    server.server_close()
    thread.join()


def _resolve_as(monkeypatch, answers):
    """``rebind.test`` returns ``answers[i]`` on lookup i (last one repeats)."""
    real = socket.getaddrinfo
    calls = []

    def resolve(name, port=None, *args, **kwargs):
        if name != "rebind.test":
            return real(name, port, *args, **kwargs)
        ip = answers[min(len(calls), len(answers) - 1)]
        calls.append(ip)
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (ip, int(port or 0)))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


def test_url_reader_refuses_internal_host(monkeypatch, internal):
    from praisonai.adapters.readers import URLReader

    port, hits = internal
    _resolve_as(monkeypatch, ["127.0.0.1"])  # no check at all before this change
    docs = URLReader().load(f"http://rebind.test:{port}/")
    assert hits == []
    assert "INTERNAL-ONLY-CANARY" not in str(docs)


def test_image_download_cannot_be_rebound(monkeypatch, internal, tmp_path):
    from praisonai.capabilities.images import _download_image

    port, hits = internal
    _resolve_as(monkeypatch, [PUBLIC, "127.0.0.1"])
    with pytest.raises(Exception):
        _download_image(f"http://rebind.test:{port}/img.png", str(tmp_path / "img.png"))
    assert hits == []
    assert not (tmp_path / "img.png").exists()


@pytest.mark.parametrize("ip", ["64:ff9b::7f00:1", "::7f00:1", "100.64.0.1", "100.100.100.200"])
def test_webhook_screen_uses_the_shared_classifier(monkeypatch, ip):
    from praisonai.jobs.models import resolve_validated_webhook_targets

    _resolve_as(monkeypatch, [ip])
    with pytest.raises(ValueError):
        resolve_validated_webhook_targets("http://rebind.test/hook")
