"""Regression tests for issue #5848: remote MCP tool failures are structured.

SSE, HTTP-stream and WebSocket tool wrappers used to return a flat
``"Error: ..."`` string (``"Error: "`` on timeout), so the agent's retry
policy and circuit breaker never engaged for them.
"""
import asyncio
import importlib
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

from praisonaiagents.mcp.mcp_schema_utils import remote_tool_error

REMOTE_TOOLS = [
    ("praisonaiagents.mcp.mcp_http_stream", "HTTPStreamMCPTool"),
    ("praisonaiagents.mcp.mcp_sse", "SSEMCPTool"),
    ("praisonaiagents.mcp.mcp_websocket", "WebSocketMCPTool"),
]


@pytest.fixture
def loop():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    yield loop
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2)
    loop.close()


def _make_tool(module_name, class_name, loop, call_tool, timeout=5):
    module = importlib.import_module(module_name)
    session = MagicMock()
    session.call_tool = call_tool
    tool = getattr(module, class_name)(
        name="lookup", description="Lookup", session=session, input_schema={}, timeout=timeout,
    )
    tool._loop = loop
    return tool


@pytest.mark.parametrize("module_name, class_name", REMOTE_TOOLS)
def test_remote_tool_timeout_is_structured(module_name, class_name, loop):
    async def hang(*_args, **_kwargs):
        await asyncio.sleep(10)

    tool = _make_tool(module_name, class_name, loop, hang, timeout=0.05)
    result = tool()
    assert result == {
        "error": "MCP tool call timed out after 0.05 seconds",
        "timeout": True,
        "mcp_error": True,
    }


@pytest.mark.parametrize("module_name, class_name", REMOTE_TOOLS)
def test_remote_tool_transport_error_is_structured(module_name, class_name, loop):
    tool = _make_tool(module_name, class_name, loop, AsyncMock(side_effect=ConnectionError("connection reset")))
    result = tool()
    assert result == {
        "error": "MCP tool 'lookup' failed: ConnectionError: connection reset",
        "mcp_error": True,
    }


def test_remote_tool_error_keeps_exception_type_when_message_empty():
    class ReadTimeout(Exception):
        pass

    assert remote_tool_error("t", ReadTimeout(), 3)["error"] == "MCP tool 't' failed: ReadTimeout"


def test_agent_retries_transient_remote_mcp_failure(monkeypatch, loop):
    """The agent's existing retry loop now re-drives a transient remote MCP failure."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from types import SimpleNamespace

    from praisonaiagents import Agent
    from praisonaiagents.tools.retry import RetryPolicy

    call_tool = AsyncMock(side_effect=[
        ConnectionError("connection reset"),
        SimpleNamespace(isError=False, content=[SimpleNamespace(text="ok")]),
    ])
    tool = _make_tool("praisonaiagents.mcp.mcp_http_stream", "HTTPStreamMCPTool", loop, call_tool)
    agent = Agent(name="t", instructions="x", tools=[tool], llm="gpt-4o-mini")
    agent._tool_retry_policy = RetryPolicy(max_attempts=3, initial_delay_ms=0, max_delay_ms=0)

    assert agent._execute_tool_with_circuit_breaker("lookup", {}) == "ok"
    assert call_tool.await_count == 2
