"""Regression tests for issue #5806 (hooked async tool context, cancel-aware backoff, dead MCP runner)."""
import asyncio
import queue
import threading

import pytest

from praisonaiagents import Agent
from praisonaiagents.hooks import before_tool
from praisonaiagents.mcp.mcp import MCPToolRunner
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


def _fake_runner(dead=None, init_error=None):
    runner = MCPToolRunner.__new__(MCPToolRunner)
    runner.initialized = threading.Event()
    runner.initialized.set()
    runner._init_error = init_error
    runner._dead = dead
    runner.queue = queue.Queue()
    runner.timeout = 1
    runner.server_params = None
    runner.resources = []
    runner.stop = lambda timeout=None: None
    return runner


def _patch_runner_factory(monkeypatch, factory):
    import praisonaiagents.mcp.mcp as m

    created = []

    def make(params, timeout):
        r = factory()
        created.append(r)
        return r

    monkeypatch.setattr(m, "MCPToolRunner", make)
    return created


def test_failed_restart_stays_eligible_for_retry(monkeypatch):
    from praisonaiagents.mcp.mcp import MCP

    mcp = MCP.__new__(MCP)
    mcp.runner = _fake_runner(dead="lost")
    created = _patch_runner_factory(monkeypatch, lambda: _fake_runner(init_error="boom"))
    assert mcp._call_stdio_tool("t", {}) == "Error: boom"
    assert mcp._call_stdio_tool("t", {}) == "Error: boom"
    assert len(created) == 2


def test_restart_after_shutdown_is_refused(monkeypatch):
    from praisonaiagents.mcp.mcp import MCP

    mcp = MCP.__new__(MCP)
    mcp.runner = _fake_runner(dead="lost")
    mcp._closing = True
    created = _patch_runner_factory(monkeypatch, _fake_runner)
    assert mcp._call_stdio_tool("t", {}) == "Error: lost"
    assert created == []


def test_resource_helpers_follow_restarted_runner(monkeypatch):
    from praisonaiagents.mcp.mcp import MCP

    mcp = MCP.__new__(MCP)
    old = _fake_runner()
    old.resources = [object()]
    old.resource_templates = []
    old.prompts = []
    old.tools = []
    mcp.runner = old
    read = {fn.__name__: fn for fn in mcp._generate_resource_tools()}["read_mcp_resource"]
    old._dead = "lost"
    fresh = _fake_runner()
    fresh.read_resource = lambda uri: f"fresh:{uri}"
    _patch_runner_factory(monkeypatch, lambda: fresh)
    assert read("x://1") == "fresh:x://1"
    assert mcp.runner is fresh


def test_request_enqueued_after_drain_is_answered():
    runner = _fake_runner()

    class LateDeath(queue.Queue):
        def put(self, item, *a, **k):
            super().put(item, *a, **k)
            runner._dead = "lost"  # runner died and drained just before our put landed

    runner.queue = LateDeath()
    assert runner._dispatch("resource", "x", None) == (False, "lost")


def test_stop_cancels_runner_hung_in_initialize(monkeypatch):
    import contextlib
    import praisonaiagents.mcp.mcp as m

    transport_closed = threading.Event()

    @contextlib.asynccontextmanager
    async def fake_stdio_client(params):
        try:
            yield None, None
        finally:
            transport_closed.set()  # where the real client reaps the child

    class HangingSession:
        def __init__(self, read, write):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def initialize(self):
            await asyncio.sleep(3600)

    monkeypatch.setattr(m, "stdio_client", fake_stdio_client, raising=False)
    monkeypatch.setattr(m, "ClientSession", HangingSession, raising=False)

    runner = m.MCPToolRunner(None, timeout=5)
    assert not runner.initialized.wait(timeout=0.3)
    runner.stop(timeout=2)
    assert not runner.is_alive()
    assert transport_closed.is_set()
    assert runner._init_error == "MCP initialization cancelled"


def test_stop_before_loop_starts_is_honoured(monkeypatch):
    import praisonaiagents.mcp.mcp as m

    runner = MCPToolRunner.__new__(MCPToolRunner)
    threading.Thread.__init__(runner, daemon=True)
    runner.initialized = threading.Event()
    runner.queue = queue.Queue()
    runner._init_error = None
    runner._dead = None
    runner._loop = None
    runner._main_task = None
    runner._stop_requested = True
    monkeypatch.setattr(m, "stdio_client", lambda p: pytest.fail("spawned"), raising=False)
    asyncio.run(runner._run_async())
    assert runner._init_error == "MCP initialization cancelled"
