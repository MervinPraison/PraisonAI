"""Regression tests for issue #5806 (hooked async tool context, cancel-aware backoff, dead MCP runner)."""
import asyncio
import queue
import threading

import pytest

from praisonaiagents import Agent
from praisonaiagents.hooks import before_tool
from praisonaiagents.session.context import get_session_context, set_session_context


def test_hooked_async_tool_keeps_context_vars(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    @before_tool
    def audit(req):
        return req

    async def awhoami() -> str:
        "current user (async)"
        return get_session_context().user_id

    async def run():
        agent = Agent(name="t", instructions="x", tools=[awhoami], hooks=[audit], llm="gpt-4o-mini")
        set_session_context(user_id="alice", platform="telegram")
        return await agent.execute_tool_async("awhoami", {})

    assert asyncio.run(run()) == "alice"


def test_recovery_backoff_aborts_when_cancelled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    import praisonaiagents.agent.chat_mixin as cm

    class Boom:
        def __getattr__(self, name):
            def fail(*a, **k):
                raise Exception("429 rate limit exceeded")
            return fail

    slept = []
    monkeypatch.setattr(cm.time, "sleep", lambda s: slept.append(s))
    agent = Agent(name="t", instructions="x", llm="gpt-4o-mini")
    agent._unified_dispatcher = Boom()
    cancel = threading.Event()
    cancel.set()
    cancel.reason = "user"
    with pytest.raises(InterruptedError, match="user"):
        agent._chat_completion([{"role": "user", "content": "hi"}], cancel_token=cancel)
    assert slept == []


def test_sleep_unless_cancelled_sleeps_without_token(monkeypatch):
    import praisonaiagents.agent.chat_mixin as cm

    slept = []
    monkeypatch.setattr(cm.time, "sleep", lambda s: slept.append(s))
    clock = iter([0.0, 0.0, 0.3, 0.6])
    monkeypatch.setattr(cm.time, "monotonic", lambda: next(clock))
    cm._sleep_unless_cancelled(0.5)
    assert slept == [0.2, 0.2]


def test_dead_mcp_runner_fails_fast_with_message():
    from praisonaiagents.mcp.mcp import MCPToolRunner

    runner = MCPToolRunner.__new__(MCPToolRunner)
    runner.initialized = threading.Event()
    runner.initialized.set()
    runner._init_error = None
    runner._dead = "MCP server connection lost: Connection closed"
    runner.queue = queue.Queue()
    runner.timeout = 1
    assert runner.call_tool("ping", {}) == "Error: MCP server connection lost: Connection closed"
    assert runner._dispatch("resource", "x", None) == (False, runner._dead)
    assert runner.queue.empty()
