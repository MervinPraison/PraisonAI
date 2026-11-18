"""T-08, mcp/: cleanup failures outside finalizers are logged at debug.

Blocks reachable from ``__del__``, atexit or a finalizer callback stay silent
on purpose: logging during interpreter shutdown can fail or print noise.
"""
import ast
import asyncio
import logging
import queue
from pathlib import Path

import pytest

import praisonaiagents.mcp.mcp as mcp_mod
from praisonaiagents.mcp.mcp import MCPToolRunner

MCP_DIR = Path(mcp_mod.__file__).parent

# (file, function) pairs allowed to keep a silent broad except: finalizer paths.
FINALIZER_PATHS = {
    ("mcp.py", "__del__"), ("mcp.py", "_shutdown"), ("mcp.py", "_close_transport_clients"),
    ("mcp.py", "stop"),
    ("mcp_http_stream.py", "__del__"), ("mcp_http_stream.py", "_force_cleanup"),
    ("mcp_http_stream.py", "_cleanup_callback"), ("mcp_http_stream.py", "_cleanup_all_clients"),
    ("mcp_websocket.py", "__del__"),
    ("mcp_schema_utils.py", "cleanup"),
}


def _silent_broad(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for n in ast.walk(tree):
        if not (isinstance(n, ast.ExceptHandler) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass)):
            continue
        els = n.type.elts if isinstance(n.type, ast.Tuple) else [n.type]
        if n.type is None or any(getattr(e, "id", None) in ("Exception", "BaseException") for e in els):
            owner = [f.name for f in funcs if f.lineno <= n.lineno <= f.end_lineno]
            yield (path.name, owner[-1] if owner else "<module>")


def test_only_finalizer_paths_stay_silent():
    found = {pair for p in sorted(MCP_DIR.glob("*.py")) for pair in _silent_broad(p)}
    assert found <= FINALIZER_PATHS, found - FINALIZER_PATHS


def _records(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


def test_unanswerable_pending_request_is_logged(caplog):
    runner = object.__new__(MCPToolRunner)
    runner.queue = queue.Queue()
    runner._dead, runner._init_error = "gone", None

    class _Full:
        def put(self, *a, **k):
            raise queue.Full

    runner.queue.put((_Full(), "call"))
    with caplog.at_level(logging.DEBUG, logger=mcp_mod.logger.name):
        runner._fail_pending()
    assert _records(caplog, "could not answer a pending request")


class _BadContext:
    def __init__(self):
        self.exited = False

    async def __aexit__(self, *a):
        self.exited = True
        raise RuntimeError("exit failed")


def test_http_stream_context_exit_failures_are_logged(caplog):
    mod = pytest.importorskip("praisonaiagents.mcp.mcp_http_stream")
    client = object.__new__(mod.HTTPStreamMCPClient)
    client._session_context, client._streams_context = _BadContext(), _BadContext()
    streams = client._streams_context
    with caplog.at_level(logging.DEBUG, logger=mod.logger.name):
        asyncio.run(client._cleanup_contexts())
    assert streams.exited  # the second context is still exited
    assert _records(caplog, "session context exit failed")
    assert _records(caplog, "streams context exit failed")


def test_websocket_aclose_failures_are_logged(caplog):
    mod = pytest.importorskip("praisonaiagents.mcp.mcp_websocket")
    client = object.__new__(mod.WebSocketMCPClient)
    client._closed, client._session_context = False, _BadContext()

    class _Transport:
        async def close(self):
            raise RuntimeError("close failed")

    client.transport = _Transport()
    with caplog.at_level(logging.DEBUG, logger=mod.logger.name):
        asyncio.run(client.aclose())
    assert client._closed
    assert _records(caplog, "WebSocket MCP: session context exit failed")
    assert _records(caplog, "WebSocket MCP: transport close failed")
