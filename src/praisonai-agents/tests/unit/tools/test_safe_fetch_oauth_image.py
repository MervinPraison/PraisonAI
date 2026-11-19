"""MCP OAuth requests and image downloads cannot be steered to a loopback service.

Each call site used to check the host (or not at all) and then let its own
HTTP client resolve it again. The stub resolver answers a public address for
the first ``public_lookups`` queries of ``rebind.test`` and 127.0.0.1 after
that; a loopback TCP listener plays the internal service and counts every
connection. A pinned request either dials the public address (refused by the
conftest egress guard) or is refused by the check; it never connects to the
listener. No test reaches the network.
"""
from __future__ import annotations

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
def listener():
    """Loopback TCP listener; yields (port, accepted connection count list)."""
    accepted = []
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    srv.settimeout(0.2)
    stop = threading.Event()

    def run():
        while not stop.is_set():
            try:
                conn, _ = srv.accept()
            except OSError:
                continue
            accepted.append(1)
            conn.close()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    yield srv.getsockname()[1], accepted
    stop.set()
    thread.join()
    srv.close()


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


def _run(fn):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a refusal is the expected outcome
        return exc


def test_oauth_metadata_fetch_is_pinned(monkeypatch, listener):
    from praisonaiagents.mcp.oauth_discovery import _get_json

    port, accepted = listener
    _rebind(monkeypatch, public_lookups=1)
    _run(lambda: _get_json(f"https://rebind.test:{port}/.well-known/oauth-authorization-server", timeout=2))
    assert accepted == []


def test_oauth_registration_is_pinned(monkeypatch, listener):
    from praisonaiagents.mcp.oauth_registration import register_client

    port, accepted = listener
    _rebind(monkeypatch, public_lookups=1)
    _run(lambda: register_client(f"https://rebind.test:{port}/register",
                                 redirect_uris=["http://127.0.0.1:19876/cb"], timeout=2))
    assert accepted == []


@pytest.mark.parametrize("public_lookups", [0, 1])
def test_oauth_code_exchange_is_checked_and_pinned(monkeypatch, listener, tmp_path, public_lookups):
    from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage
    from praisonaiagents.mcp.oauth_provider import MCPOAuthProvider

    port, accepted = listener
    _rebind(monkeypatch, public_lookups=public_lookups)
    provider = MCPOAuthProvider("x", "https://api.example.com/mcp",
                                storage=MCPAuthStorage(filepath=str(tmp_path / "a.json")))
    _run(lambda: provider._exchange_code(
        {"token_endpoint": f"https://rebind.test:{port}/token"},
        {"client_id": "c", "client_secret": "SECRET"}, "code", "verifier", 2))
    assert accepted == []


def test_oauth_refresh_is_pinned(monkeypatch, listener, tmp_path):
    from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage
    from praisonaiagents.mcp.oauth_provider import MCPOAuthProvider

    port, accepted = listener
    _rebind(monkeypatch, public_lookups=1)
    provider = MCPOAuthProvider("x", "https://api.example.com/mcp",
                                storage=MCPAuthStorage(filepath=str(tmp_path / "a.json")))
    entry = {
        "tokens": {"refresh_token": "r", "token_endpoint": f"https://rebind.test:{port}/token"},
        "client_info": {"client_id": "c", "client_secret": "SECRET"},
    }
    assert provider._try_refresh(entry) is False
    assert accepted == []


def test_image_result_download_is_checked_and_pinned(monkeypatch, listener, tmp_path):
    from praisonaiagents.agent._image_result import ImageResult

    port, accepted = listener
    _rebind(monkeypatch, public_lookups=0)
    result = ImageResult({"data": [{"url": f"http://rebind.test:{port}/img.png"}]})
    _run(lambda: result.save(str(tmp_path / "out.png")))
    assert accepted == []
    assert not (tmp_path / "out.png").exists()


def test_oauth_loopback_server_still_allowed(monkeypatch):
    """Local MCP servers on loopback keep working (named loopback hosts only)."""
    from praisonaiagents.mcp import oauth_discovery
    from praisonaiagents.tools import url_safety

    seen = {}

    def fake_fetch(url, **kwargs):
        seen.update(kwargs, url=url)
        raise RuntimeError("stop")

    monkeypatch.setattr(url_safety, "safe_fetch", fake_fetch)
    with pytest.raises(RuntimeError):
        oauth_discovery._send("GET", "http://localhost:8080/x", 2)
    assert seen["url"] == "http://localhost:8080/x"
    assert "localhost" in seen["allowlist"]
