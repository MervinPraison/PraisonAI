"""Tests for tool-call identity exposed through middleware context."""

from __future__ import annotations

import pytest
from praisonaiagents import Agent
from praisonaiagents.hooks import wrap_tool_call


def test_sync_tool_middleware_receives_original_tool_call_id():
    observed_ids: list[str | None] = []
    handler_calls: list[str] = []

    @wrap_tool_call
    def capture_identity(request, call_next):
        observed_ids.append(request.context.metadata.get("tool_call_id"))
        return call_next(request)

    def inert_tool(value: str) -> str:
        handler_calls.append(value)
        return "completed"

    agent = Agent(
        name="sync-middleware-identity",
        instructions="Exercise one inert test tool.",
        tools=[inert_tool],
        hooks=[capture_identity],
        approval=True,
    )

    result = agent.execute_tool(
        "inert_tool", {"value": "synthetic-value"}, "sync-tool-call-001"
    )

    assert result == "completed"
    assert handler_calls == ["synthetic-value"]
    assert observed_ids == ["sync-tool-call-001"]


@pytest.mark.asyncio
async def test_async_tool_middleware_receives_original_tool_call_id():
    observed_ids: list[str | None] = []
    handler_calls: list[str] = []

    @wrap_tool_call
    def capture_identity(request, call_next):
        observed_ids.append(request.context.metadata.get("tool_call_id"))
        return call_next(request)

    async def inert_tool(value: str) -> str:
        handler_calls.append(value)
        return "completed"

    agent = Agent(
        name="async-middleware-identity",
        instructions="Exercise one inert test tool.",
        tools=[inert_tool],
        hooks=[capture_identity],
        approval=True,
    )

    result = await agent.execute_tool_async(
        "inert_tool", {"value": "synthetic-value"}, "async-tool-call-001"
    )

    assert result == "completed"
    assert handler_calls == ["synthetic-value"]
    assert observed_ids == ["async-tool-call-001"]
