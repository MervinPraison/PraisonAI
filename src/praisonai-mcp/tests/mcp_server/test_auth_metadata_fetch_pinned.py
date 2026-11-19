"""OAuth/OIDC metadata fetches cannot reach a loopback service.

``fetch_client_metadata`` fetches a URL the connecting client names
(Client ID Metadata Document), and the protected-resource / authorization
server discovery helpers fetch remote metadata. A loopback HTTP server plays
the internal service; the hostname ``internal.test`` resolves to 127.0.0.1.
No test reaches the network.
"""
from __future__ import annotations

import asyncio
import http.server
import socket
import threading

import pytest


@pytest.fixture(autouse=True)
def _no_opt_outs(monkeypatch):
    for name in ("ALLOW_LOCAL_CRAWL", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                 "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    real = socket.getaddrinfo

    def resolve(name, port=None, *args, **kwargs):
        if name == "internal.test":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", int(port or 0)))]
        return real(name, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


@pytest.fixture
def internal():
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            body = b'{"client_id": "x", "issuer": "x"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
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


def _run(coro):
    try:
        return asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 - a refusal is the expected outcome
        return exc


def test_client_metadata_url_is_checked(internal):
    from praisonai_mcp.mcp_server.auth.oidc import fetch_client_metadata

    port, hits = internal
    _run(fetch_client_metadata(f"http://internal.test:{port}/client.json"))
    assert hits == []


def test_protected_resource_metadata_is_checked(internal):
    from praisonai_mcp.mcp_server.auth.oidc import fetch_protected_resource_metadata

    port, hits = internal
    _run(fetch_protected_resource_metadata(f"http://internal.test:{port}"))
    assert hits == []


def test_authorization_server_discovery_is_checked(internal):
    from praisonai_mcp.mcp_server.auth.oauth import discover_oauth_metadata

    port, hits = internal
    _run(discover_oauth_metadata(f"http://internal.test:{port}"))
    assert hits == []


def test_authorization_server_client_metadata_is_checked(internal):
    """The built-in authorization server fetches the URL a connecting client names."""
    from praisonai_mcp.mcp_server.auth.server import fetch_client_metadata
    from praisonaiagents.tools.url_safety import UnsafeURLError

    port, hits = internal
    with pytest.raises(UnsafeURLError):
        fetch_client_metadata(f"https://internal.test:{port}/client.json")
    assert hits == []
