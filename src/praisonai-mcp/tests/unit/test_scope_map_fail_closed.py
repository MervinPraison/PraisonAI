"""Every MCP method a scoped key can call is mapped; unmapped ones fail closed."""

import asyncio

from praisonai_mcp.mcp_server.auth.scopes import OPERATION_SCOPES
from praisonai_mcp.mcp_server.server import MCPServer

PUBLIC = {"initialize", "ping"}


def _call(server, method, scopes):
    msg = {"jsonrpc": "2.0", "id": 1, "method": method, "params": {}}
    return asyncio.run(server.handle_message(msg, granted_scopes=scopes))


def test_every_handler_has_a_scope_or_is_public():
    server = MCPServer(name="t")
    assert set(server._handlers) - PUBLIC <= set(OPERATION_SCOPES)


def test_tools_search_needs_tools_read():
    server = MCPServer(name="t")
    resp = _call(server, "tools/search", ["resources:read"])
    assert resp["error"]["message"] == "insufficient_scope"
    assert "error" not in _call(server, "tools/search", ["tools:read"])


def test_unmapped_method_fails_closed():
    server = MCPServer(name="t")
    server._handlers["custom/thing"] = lambda *a, **k: {}
    resp = _call(server, "custom/thing", ["tools:read"])
    assert resp["error"]["message"] == "insufficient_scope"
