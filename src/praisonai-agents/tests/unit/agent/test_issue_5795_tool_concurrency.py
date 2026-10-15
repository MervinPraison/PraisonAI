"""Regression tests for #5795: tool/MCP calls must not be timed out by queue wait."""
import asyncio
import concurrent.futures as cf
import queue
import threading
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

from praisonaiagents import Agent
from praisonaiagents.hooks import HookEvent, HookRegistry


def _allow_all_hooks():
    """Own registry (no leaked global hooks) with a sync BEFORE_TOOL hook,
    so parallel tool calls also run the hook concurrently."""
    registry = HookRegistry()
    registry.register_function(HookEvent.BEFORE_TOOL, lambda data: None)
    return registry


def test_parallel_sync_tools_not_timed_out_by_queue_wait():
    def slow(n: int) -> str:
        """slow tool"""
        time.sleep(0.5)
        return f"ok{n}"

    agent = Agent(name="t", instructions="x", tools=[slow], llm="gpt-4o-mini", hooks=_allow_all_hooks())
    agent._tool_timeout = 0.8
    with cf.ThreadPoolExecutor(5) as ex:
        results = list(ex.map(lambda i: agent.execute_tool("slow", {"n": i}), range(5)))
    for i, result in enumerate(results):
        assert isinstance(result, str) and result.startswith(f"ok{i}"), result


def test_parallel_async_sync_tools_not_timed_out_by_queue_wait():
    def slow(n: int) -> str:
        """slow tool"""
        time.sleep(0.5)
        return f"ok{n}"

    agent = Agent(name="a", instructions="x", tools=[slow], llm="gpt-4o-mini", hooks=_allow_all_hooks())
    agent._tool_timeout = 0.8

    async def main():
        # Twice the pool size: the second half queues for a worker first.
        return await asyncio.gather(
            *(agent.execute_tool_async("slow", {"n": i}) for i in range(10))
        )

    for i, result in enumerate(asyncio.run(main())):
        assert isinstance(result, str) and result.startswith(f"ok{i}"), result


def test_hung_async_sync_tools_do_not_starve_default_executor():
    release = threading.Event()
    tools = []
    for i in range(10):
        def hang(x: int = 0) -> str:
            """hang"""
            release.wait(10)
            return "x"
        hang.__name__ = f"hang{i}"
        tools.append(hang)

    agent = Agent(name="u", instructions="x", tools=tools, llm="gpt-4o-mini", hooks=HookRegistry())
    agent._tool_timeout = 0.2

    async def main():
        for i in range(10):
            result = await asyncio.wait_for(agent.execute_tool_async(f"hang{i}", {"x": 1}), 5)
            assert isinstance(result, dict) and result.get("timeout"), result
        # The loop's default executor is still free for other to_thread users.
        assert await asyncio.wait_for(asyncio.to_thread(lambda: 42), 2) == 42

    try:
        asyncio.run(main())
    finally:
        release.set()


def test_transport_wrapper_cancels_call_on_timeout():
    from praisonaiagents.mcp.mcp_sse import SSEMCPTool

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    finished = threading.Event()

    class _Session:
        async def call_tool(self, name, kwargs):
            await asyncio.sleep(1.0)
            finished.set()

    try:
        tool = SSEMCPTool("t", "d", _Session(), {}, timeout=0.1)
        tool._loop = loop
        result = tool()
        assert "timed out" in result
        time.sleep(1.3)
        assert not finished.is_set()
    finally:
        loop.call_soon_threadsafe(loop.stop)


def test_stdio_runner_runs_requests_concurrently_and_cancels_on_shutdown(monkeypatch):
    import praisonaiagents.mcp.mcp as mcp_mod

    class _Session:
        async def initialize(self):
            pass

        async def list_tools(self):
            return SimpleNamespace(tools=[])

        async def call_tool(self, name, arguments):
            await asyncio.sleep(10 if name == "slow" else 0)
            return name

    @asynccontextmanager
    async def _stdio_client(params):
        yield None, None

    @asynccontextmanager
    async def _client_session(read, write):
        yield _Session()

    async def _no_discovery(self, session):
        pass

    monkeypatch.setattr(mcp_mod, "stdio_client", _stdio_client)
    monkeypatch.setattr(mcp_mod, "ClientSession", _client_session)
    monkeypatch.setattr(mcp_mod.MCPToolRunner, "_discover_resources_and_prompts", _no_discovery)

    runner = mcp_mod.MCPToolRunner(None, timeout=30)
    assert runner.initialized.wait(5) and runner._init_error is None

    slow_q, fast_q = queue.Queue(), queue.Queue()
    runner.queue.put((slow_q, "tool", "slow", {}, threading.Event()))
    runner.queue.put((fast_q, "tool", "fast", {}, threading.Event()))
    # The fast call is not serialized behind the in-flight slow one.
    assert fast_q.get(timeout=2) == (True, "fast")

    runner.queue.put(None)
    ok, message = slow_q.get(timeout=2)
    assert not ok and "shut down" in message
    runner.join(2)
    assert not runner.is_alive()
