"""Bot fetches of untrusted URLs cannot reach a loopback service.

Inbound media URLs, remote instruction sources and monitor-gate URLs come from
chat messages, project config or the model. The stub resolver answers a
public address for the first ``public_lookups`` queries of ``rebind.test`` and
127.0.0.1 after that; a loopback HTTP server plays the internal service. No
stub answers a public address when a connection is made, so no test reaches
the network.
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


def test_inbound_media_rebind_is_refused(monkeypatch, internal):
    from praisonai_bot.bots._media import InboundMediaError, _fetch_url

    port, hits = internal
    _rebind(monkeypatch, public_lookups=1)
    with pytest.raises(InboundMediaError):
        _fetch_url(f"http://rebind.test:{port}/a.png", 1024)
    assert hits == []


@pytest.mark.parametrize("url", [
    "http://[64:ff9b::7f00:1]/x",      # NAT64 form of 127.0.0.1
    "http://[::ffff:169.254.169.254]/",  # IPv4-mapped metadata address
    "http://169.254.169.254:80\\@1.1.1.1/",  # backslash parser differential
])
def test_inbound_media_check_uses_shared_rules(url):
    from praisonai_bot.bots._media import is_safe_url

    assert is_safe_url(url) is False


def test_instruction_source_rebind_is_refused(monkeypatch, internal):
    from praisonai_bot.integration import context_files as ctx

    port, hits = internal
    _rebind(monkeypatch, public_lookups=1)
    assert ctx._fetch_remote_source(f"http://rebind.test:{port}/rules.md") is None
    assert hits == []


def test_monitor_gate_refuses_nat64_loopback(monkeypatch):
    from praisonai_bot.scheduler.condition_gate import MonitorGate

    def resolve(name, port=None, *args, **kwargs):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("64:ff9b::7f00:1", int(port or 0), 0, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    with pytest.raises(ValueError, match="public"):
        MonitorGate()._fetch_url("http://rebind.test/status")
