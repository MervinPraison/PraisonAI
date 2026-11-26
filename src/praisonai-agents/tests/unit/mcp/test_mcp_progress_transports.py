"""HTTP-stream, SSE, and WebSocket MCP wrappers forward progress events."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from praisonaiagents.streaming.events import StreamEventType, tool_progress_channel


@pytest.mark.parametrize(
    "module_name,class_name",
    [
        ("praisonaiagents.mcp.mcp_sse", "SSEMCPTool"),
        ("praisonaiagents.mcp.mcp_http_stream", "HTTPStreamMCPTool"),
        ("praisonaiagents.mcp.mcp_websocket", "WebSocketMCPTool"),
    ],
)
def test_remote_mcp_tool_progress_reaches_stream(module_name, class_name):
    pytest.importorskip("mcp")
    import importlib

    async def call_tool(_name, _arguments, progress_callback=None):
        assert progress_callback is not None
        await progress_callback(25, 100, "Working")
        return SimpleNamespace(
            isError=False,
            content=[SimpleNamespace(text="done")],
        )

    module = importlib.import_module(module_name)
    session = SimpleNamespace(call_tool=AsyncMock(side_effect=call_tool))
    tool = getattr(module, class_name)(
        name="long_task",
        description="Run a task.",
        session=session,
        input_schema={"type": "object", "properties": {}},
    )
    events = []
    with tool_progress_channel(events.append):
        assert asyncio.run(tool._async_call()) == "done"
    assert len(events) == 1
    assert events[0].type == StreamEventType.TOOL_PROGRESS
    assert events[0].content == "Working"
    assert events[0].metadata["progress"] == 0.25
