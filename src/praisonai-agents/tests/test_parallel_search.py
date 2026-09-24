import importlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
import json
from threading import Thread

import pytest

pytest.importorskip("mcp.client.streamable_http")

web_search_module = importlib.import_module("praisonaiagents.tools.web_search")


class MCPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        request_bytes = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        request = json.loads(request_bytes)
        self.server.requests.append(request)
        self.server.header_snapshots.append({
            "user_agent": self.headers.get("User-Agent"),
            "accept": self.headers.get("Accept"),
            "content_type": self.headers.get("Content-Type"),
            "accept_encoding": self.headers.get("Accept-Encoding"),
            "authorization_present": self.headers.get("Authorization") is not None,
        })
        method = request.get("method")
        request_id = request.get("id")

        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if method == "initialize":
            self._send_json({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": request["params"]["protocolVersion"],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "test-search", "version": "1.0"},
                },
            })
            return
        if method == "tools/list":
            description = "x" * 2000 if self.server.oversized_tools_list else "Search the web"
            self._send_json({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "web_search",
                            "description": description,
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "objective": {"type": "string"},
                                    "search_queries": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                },
                                "required": ["objective", "search_queries"],
                            },
                        },
                        {
                            "name": "web_fetch",
                            "description": "Fetch a page",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ],
                },
            })
            return
        if method == "tools/call":
            self.server.tool_calls.append(request.get("params", {}))
            text = json.dumps({
                "results": [
                    {
                        "url": "https://example.com/one",
                        "title": "First result",
                        "excerpts": ["x" * 2000 if self.server.chunked_tool_call else "Useful evidence from the first result."],
                    },
                    {
                        "url": "https://example.com/two",
                        "title": "Second result",
                        "excerpts": ["A second useful result."],
                    },
                ],
            })
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": text}], "isError": False},
            }
            if self.server.chunked_tool_call:
                self._send_chunked_json(response)
            else:
                self._send_json(response)
            return

        self._send_json({
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Method not found"},
        })

    def do_GET(self):
        self._send_chunked_json({"body": "x" * 2000})

    def do_DELETE(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_json(self, body):
        response = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def _send_chunked_json(self, body):
        response = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for offset in range(0, len(response), 64):
                chunk = response[offset:offset + 64]
                self.wfile.write(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
        except OSError:
            pass

    def log_message(self, format, *args):
        return


@pytest.fixture
def mcp_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), MCPHandler)
    server.daemon_threads = True
    server.requests = []
    server.tool_calls = []
    server.header_snapshots = []
    server.chunked_tool_call = False
    server.oversized_tools_list = False
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _server_url(server):
    return f"http://127.0.0.1:{server.server_address[1]}/mcp"


def test_parallel_is_explicit_and_does_not_change_default_order(monkeypatch):
    default_names = [name for name, _, _ in web_search_module.SEARCH_PROVIDERS]
    selectable_names = [name for name, _, _ in web_search_module.SELECTABLE_SEARCH_PROVIDERS]
    assert "parallel" not in default_names
    assert "parallel" in selectable_names

    calls = []

    def check_incumbent():
        return True, None

    def search_incumbent(query, max_results):
        calls.append(query)
        return [{"title": "Existing", "url": "https://example.com", "snippet": "", "provider": "existing"}]

    monkeypatch.setattr(web_search_module, "SEARCH_PROVIDERS", [("existing", check_incumbent, search_incumbent)])
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    result = web_search_module.search_web("default route")

    assert calls == ["default route"]
    assert result[0]["provider"] == "existing"


def test_parallel_provider_maps_results_and_never_adds_authorization(monkeypatch):
    mcp_module = importlib.import_module("praisonaiagents.mcp")
    observed = {}

    class SearchTool:
        __name__ = "web_search"

        def __call__(self, **arguments):
            observed["arguments"] = arguments
            return json.dumps({
                "results": [
                    {"url": "https://example.com/one", "title": "T" * 300, "excerpts": ["S" * 1500]},
                    {"url": "https://example.com/two", "title": "Second", "excerpts": ["Useful excerpt"]},
                    {"url": "https://example.com/three", "title": "Third", "excerpts": []},
                ],
            })

    class FakeMCP:
        def __init__(self, url, **options):
            observed["url"] = url
            observed["options"] = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def get_tools(self):
            return [SearchTool()]

    monkeypatch.setattr(mcp_module, "MCP", FakeMCP)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    query = "PraisonAI provider configuration"
    result = web_search_module.search_web(query, max_results=2, providers="parallel")

    assert observed["url"] == web_search_module.PARALLEL_SEARCH_MCP_URL
    assert observed["options"]["allowed_tools"] == ["web_search"]
    assert observed["options"]["timeout"] == web_search_module.PARALLEL_SEARCH_TIMEOUT_SECONDS
    assert observed["options"]["max_response_bytes"] == web_search_module.PARALLEL_MAX_RESPONSE_BYTES
    assert observed["options"]["headers"] == {"User-Agent": f"praisonaiagents/{version('praisonaiagents')}"}
    assert "Authorization" not in observed["options"]["headers"]
    assert observed["arguments"] == {"objective": query, "search_queries": [query]}
    assert len(result) == 2
    assert result[0]["provider"] == "parallel"
    assert len(result[0]["title"]) == web_search_module.PARALLEL_MAX_TITLE_CHARS
    assert result[0]["title"].endswith("…")
    assert len(result[0]["snippet"]) == web_search_module.PARALLEL_MAX_SNIPPET_CHARS
    assert result[0]["snippet"].endswith("…")


@pytest.mark.parametrize("response", ["null", "[]", "{}", '{"other": []}', '{"results": {}}'])
def test_parallel_rejects_malformed_result_shape(monkeypatch, response):
    mcp_module = importlib.import_module("praisonaiagents.mcp")

    class SearchTool:
        __name__ = "web_search"

        def __call__(self, **arguments):
            return response

    class FakeMCP:
        def __init__(self, url, **options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def get_tools(self):
            return [SearchTool()]

    monkeypatch.setattr(mcp_module, "MCP", FakeMCP)

    with pytest.raises(ValueError):
        web_search_module._search_parallel("search query")


def test_parallel_accepts_valid_empty_results(monkeypatch):
    mcp_module = importlib.import_module("praisonaiagents.mcp")

    class SearchTool:
        __name__ = "web_search"

        def __call__(self, **arguments):
            return '{"results": []}'

    class FakeMCP:
        def __init__(self, url, **options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def get_tools(self):
            return [SearchTool()]

    monkeypatch.setattr(mcp_module, "MCP", FakeMCP)

    assert web_search_module._search_parallel("search query") == []


def test_parallel_uses_real_mcp_caller_and_preserves_request_headers(mcp_server, monkeypatch):
    monkeypatch.setattr(web_search_module, "PARALLEL_SEARCH_MCP_URL", _server_url(mcp_server))
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "parallel")
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    query = "PraisonAI web search provider"

    result = web_search_module.search_web(query, max_results=1)

    assert result == [{
        "title": "First result",
        "url": "https://example.com/one",
        "snippet": "Useful evidence from the first result.",
        "provider": "parallel",
    }]
    assert len(mcp_server.tool_calls) == 1
    assert mcp_server.tool_calls[0]["name"] == "web_search"
    assert mcp_server.tool_calls[0]["arguments"] == {"objective": query, "search_queries": [query]}
    assert mcp_server.header_snapshots
    assert all(snapshot["user_agent"] == f"praisonaiagents/{version('praisonaiagents')}" for snapshot in mcp_server.header_snapshots)
    assert all("application/json" in snapshot["accept"] and "text/event-stream" in snapshot["accept"] for snapshot in mcp_server.header_snapshots)
    assert all(snapshot["content_type"] == "application/json" for snapshot in mcp_server.header_snapshots)
    assert all(snapshot["accept_encoding"] == "identity" for snapshot in mcp_server.header_snapshots)
    assert all(not snapshot["authorization_present"] for snapshot in mcp_server.header_snapshots)


def test_parallel_streaming_response_limit_is_enforced(mcp_server, monkeypatch):
    import asyncio
    from httpx import Timeout
    from praisonaiagents.mcp.mcp_http_stream import _bounded_httpx_client_factory

    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")

    async def read_oversized_response():
        factory = _bounded_httpx_client_factory(512)
        async with factory(timeout=Timeout(2)) as client:
            async with client.stream("GET", _server_url(mcp_server)) as response:
                async for _ in response.aiter_bytes():
                    pass

    with pytest.raises(ValueError, match="maximum of 512 bytes"):
        asyncio.run(read_oversized_response())
