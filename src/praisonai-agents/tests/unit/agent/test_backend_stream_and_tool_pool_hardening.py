"""Regression tests for #6072: streaming bridge, async tool pool, breaker neutrality."""
import asyncio
import threading
import time

import pytest

from praisonaiagents import Agent


def _agent(**kw):
    return Agent(name="t", instructions="x", llm="gpt-4o-mini", **kw)


class _Backend:
    def __init__(self, fail_first=False):
        self.produced = 0
        self.calls = 0
        self.fail_first = fail_first

    async def stream(self, prompt, **kw):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            yield "a"
            raise RuntimeError("boom")
        for i in range(100000):
            self.produced += 1
            yield f"c{i}"
            await asyncio.sleep(0)


def test_stream_close_in_running_loop_stops_producer():
    a = _agent()
    a.backend = _Backend()

    async def main():
        g = a._delegate_streaming_to_backend("p")
        next(g)
        g.close()
        after_close = a.backend.produced
        time.sleep(0.3)
        return a.backend.produced - after_close

    produced = asyncio.run(main())
    assert produced == 0


def test_backend_runtime_error_does_not_rerun_stream():
    a = _agent()
    a.backend = _Backend(fail_first=True)

    async def main():
        with pytest.raises(RuntimeError, match="boom"):
            for _ in a._delegate_streaming_to_backend("p"):
                pass

    asyncio.run(main())
    assert a.backend.calls == 1


def test_async_sync_tool_with_timeout_uses_agent_pool():
    seen = {}

    def probe() -> str:
        seen["thread"] = threading.current_thread().name
        return "ok"

    a = _agent(tools=[probe])
    a._tool_timeout = 5
    assert asyncio.run(a.execute_tool_async("probe", {})) == "ok"
    assert seen["thread"].startswith("tool-t")


def test_async_timed_out_tool_does_not_hold_default_executor():
    def hang() -> str:
        time.sleep(2)
        return "ok"

    a = _agent(tools=[hang])
    a._tool_timeout = 0.1

    async def main():
        tasks = [asyncio.create_task(a.execute_tool_async("hang", {})) for _ in range(40)]
        await asyncio.gather(*tasks)
        start = time.monotonic()
        await asyncio.to_thread(lambda: 1)
        return time.monotonic() - start

    assert asyncio.run(main()) < 1.0


def test_caller_errors_do_not_open_breaker():
    def read_file(path: str) -> str:
        raise FileNotFoundError(path)

    a = _agent(tools=[read_file])
    for i in range(7):
        result = a._execute_tool_with_circuit_breaker_impl("read_file", {"path": f"/nope{i}"})
        assert not result.get("circuit_open")


def test_open_breaker_remediation_uses_live_config():
    a = _agent()
    breaker = a._get_tool_circuit_breaker("x")
    breaker.config.recovery_timeout = 7
    assert "(7s)" in a._circuit_breaker_open_result("x")["remediation"]


def test_stream_close_runs_backend_cleanup():
    cleaned = threading.Event()

    class _CleanupBackend:
        async def stream(self, prompt, **kw):
            try:
                while True:
                    yield "c"
                    await asyncio.sleep(0)
            finally:
                cleaned.set()

    a = _agent()
    a.backend = _CleanupBackend()
    g = a._delegate_streaming_to_backend("p")
    next(g)
    g.close()
    assert cleaned.wait(2)


def test_parallel_healthy_timed_tools_do_not_queue_into_timeout():
    def work(i: int) -> str:
        time.sleep(0.6)
        return "ok"

    a = _agent(tools=[work])
    a._tool_timeout = 1

    async def main():
        return await asyncio.gather(*(a.execute_tool_async("work", {"i": i}) for i in range(5)))

    # Loop-guard may append advisory notes; what matters is no timeout.
    assert all(isinstance(r, str) and r.startswith("ok") for r in asyncio.run(main()))
