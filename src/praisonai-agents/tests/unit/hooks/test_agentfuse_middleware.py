"""Real Agent dispatch tests for the optional AgentFuse tool middleware."""

from __future__ import annotations

import pytest
from dhms_agentfuse import RuntimeGuard
from praisonaiagents import Agent
from praisonaiagents.hooks.agentfuse import AgentFuseToolMiddleware


def _sync_agent(guard: RuntimeGuard):
    handler_calls: list[str] = []

    def protected_write(value: str) -> str:
        handler_calls.append(value)
        return "write completed"

    middleware = AgentFuseToolMiddleware(guard)
    agent = Agent(
        name="agentfuse-sync-test",
        instructions="Exercise one inert test tool.",
        tools=[protected_write],
        hooks=[middleware],
        approval=True,
    )
    return agent, middleware, handler_calls


def test_sync_allow_dispatches_once_and_preserves_identity():
    agent, middleware, calls = _sync_agent(
        RuntimeGuard(allow_tools={"protected_write"})
    )

    result = agent.execute_tool(
        "protected_write", {"value": "synthetic-value"}, "praison-allow-001"
    )

    assert result == "write completed"
    assert calls == ["synthetic-value"]
    assert middleware.decision_for("praison-allow-001").tool_call_id == (
        "praison-allow-001"
    )


def test_sync_block_returns_non_execution_without_dispatch():
    agent, middleware, calls = _sync_agent(RuntimeGuard(deny_tools={"protected_write"}))

    result = agent.execute_tool(
        "protected_write", {"value": "synthetic-value"}, "praison-block-001"
    )

    assert calls == []
    assert result["status"] == "blocked"
    assert result["tool_failure"] is False
    assert result["host_execution"] == {
        "outcome": "not_executed",
        "handler_started": False,
    }
    assert result["agentfuse_decision"]["tool_call_id"] == "praison-block-001"
    assert middleware.decision_for("praison-block-001").action == "block"


def test_sync_policy_failure_fails_closed_without_dispatch():
    def failing_policy(tool_call):
        del tool_call
        raise RuntimeError("synthetic policy failure")

    agent, middleware, calls = _sync_agent(RuntimeGuard(policy=failing_policy))

    result = agent.execute_tool(
        "protected_write", {"value": "synthetic-value"}, "praison-failure-001"
    )

    assert calls == []
    assert result["status"] == "blocked"
    assert result["agentfuse_decision"]["reason_code"] == "policy_exception"
    assert result["host_execution"]["handler_started"] is False
    assert middleware.decision_for("praison-failure-001").reason_code == (
        "policy_exception"
    )


@pytest.mark.asyncio
async def test_async_dispatch_uses_same_guard_and_preserves_identity():
    handler_calls: list[str] = []

    async def protected_write(value: str) -> str:
        handler_calls.append(value)
        return "write completed"

    middleware = AgentFuseToolMiddleware(RuntimeGuard(deny_tools={"protected_write"}))
    agent = Agent(
        name="agentfuse-async-test",
        instructions="Exercise one inert test tool.",
        tools=[protected_write],
        hooks=[middleware],
        approval=True,
    )

    result = await agent.execute_tool_async(
        "protected_write", {"value": "synthetic-value"}, "praison-async-001"
    )

    assert handler_calls == []
    assert result["host_execution"]["outcome"] == "not_executed"
    assert result["agentfuse_decision"]["tool_call_id"] == "praison-async-001"
