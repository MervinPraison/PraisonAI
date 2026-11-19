"""URL loaders cannot be steered to an internal service by DNS rebinding.

Each loader used to check the host and then let its HTTP client resolve it
again. The stub resolver below answers a public address for the first
``public_lookups`` queries and 127.0.0.1 afterwards; a loopback server plays
the internal service. A pinned fetch either dials the public address (the
conftest egress guard refuses it) or is refused by the check; it never reaches
the loopback server. No test reaches the network.
"""
from __future__ import annotations

import http.server
import socket
import threading
import types

import pytest

pytest.importorskip("httpx")

PUBLIC = "93.184.216.34"
CANARY = b"INTERNAL-ONLY-CANARY"


@pytest.fixture(autouse=True)
def _no_opt_outs(monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def internal():
    """A loopback 'internal service'; yields (port, hits)."""
    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(CANARY) + 2))
            self.end_headers()
            self.wfile.write(b'"' + CANARY + b'"')

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


def test_knowledge_url_loader(monkeypatch, internal):
    pytest.importorskip("markitdown")
    from markitdown import MarkItDown
    from praisonaiagents.knowledge.knowledge import Knowledge

    port, hits = internal
    _rebind(monkeypatch, public_lookups=1)
    kb = types.SimpleNamespace(
        markdown=MarkItDown(),
        chunker=types.SimpleNamespace(chunk=lambda text: [text]),
        store=lambda text, **kw: {"results": [{"memory": text}]},
    )
    with pytest.raises(Exception):
        Knowledge._process_url(kb, f"http://rebind.test:{port}/doc.json")
    assert hits == []


def test_download_file(monkeypatch, internal, tmp_path):
    from praisonaiagents.tools.file_tools import FileTools
    from praisonaiagents.approval import reset_yaml_approved_tools, set_yaml_approved_tools

    port, hits = internal
    monkeypatch.chdir(tmp_path)
    tools = FileTools()
    monkeypatch.setattr(tools, "_require_workspace_access", lambda write=False: None)
    monkeypatch.setattr(tools, "_validate_path", lambda p: str(tmp_path / p))
    _rebind(monkeypatch, public_lookups=1)
    token = set_yaml_approved_tools(["download_file"])
    try:
        result = tools.download_file(f"http://rebind.test:{port}/x", "out.bin")
    finally:
        reset_yaml_approved_tools(token)
    assert hits == []
    assert not result["success"]


def test_url_mention(monkeypatch, internal):
    from praisonaiagents.tools.mentions import MentionsParser

    port, hits = internal
    _rebind(monkeypatch, public_lookups=2)  # SpiderTools' own pre-check resolves twice
    text = MentionsParser()._process_url_mention(f"http://rebind.test:{port}/")
    assert hits == []
    assert "INTERNAL-ONLY-CANARY" not in (text or "")


def test_openapi_operation(monkeypatch, internal):
    from praisonaiagents.tools.openapi_toolset import OpenAPIToolset

    port, hits = internal
    spec = {"openapi": "3.0.0", "servers": [{"url": f"http://rebind.test:{port}"}],
            "paths": {"/meta": {"get": {"operationId": "getMeta"}}}}
    tool = OpenAPIToolset(spec_dict=spec).get_tools()[0]
    _rebind(monkeypatch, public_lookups=1)
    result = tool()
    assert hits == []
    assert "INTERNAL-ONLY-CANARY" not in str(result)


def test_openapi_spec_url(monkeypatch, internal):
    from praisonaiagents.tools.openapi_toolset import OpenAPIToolset

    port, hits = internal
    _rebind(monkeypatch, public_lookups=1)
    with pytest.raises(Exception):
        OpenAPIToolset(spec_url=f"http://rebind.test:{port}/openapi.json")
    assert hits == []
