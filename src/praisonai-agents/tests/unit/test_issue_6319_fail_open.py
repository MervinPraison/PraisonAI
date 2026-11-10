"""Regression tests for #6319: async hooks via register_function, failed
BackgroundTask.wait(), and ReliabilityEvaluator stale/crashed runs."""
import asyncio

import pytest

from praisonaiagents.background import BackgroundRunner
from praisonaiagents.eval.reliability import ReliabilityEvaluator
from praisonaiagents.hooks import (
    BeforeToolInput, HookEvent, HookRegistry, HookResult, HookRunner,
)


def _before_tool():
    return BeforeToolInput(session_id="s", cwd=".", event_name="before_tool",
                           timestamp="0", tool_name="rm", tool_input={})


def test_async_register_function_hook_denies():
    reg = HookRegistry()

    async def deny_rm(data):
        return HookResult.deny("no rm")

    reg.register_function(HookEvent.BEFORE_TOOL, deny_rm)
    res = HookRunner(reg).execute_sync(HookEvent.BEFORE_TOOL, _before_tool())
    assert res[0].output.decision == "deny"


def test_background_wait_raises_on_failure_and_timeout():
    async def main():
        r = BackgroundRunner()

        def boom():
            raise ValueError("kaboom")

        async def slow():
            await asyncio.sleep(5)

        t = await r.submit(boom, name="boom")
        with pytest.raises(RuntimeError, match="kaboom"):
            await t.wait()
        t2 = await r.submit(slow, name="slow", timeout=0.1)
        with pytest.raises(RuntimeError, match="timed out after 0.1s"):
            await t2.wait()
        t3 = await r.submit(lambda: 42, name="ok")
        assert await t3.wait() == 42

    asyncio.run(main())


class _Stub:
    def __init__(self):
        self.chat_history = [{"role": "tool", "name": "search"}]

    def chat(self, q):
        self.chat_history.append({"role": "assistant", "content": "x"})
        return "x"


class _Crash:
    chat_history = []

    def chat(self, q):
        raise RuntimeError("crash")


def test_reliability_ignores_prior_history():
    assert not ReliabilityEvaluator(agent=_Stub(), input_text="q",
                                    expected_tools=["search"]).run().passed
    assert ReliabilityEvaluator(agent=_Stub(), input_text="q",
                                forbidden_tools=["search"]).run().passed


def test_reliability_crash_never_passes():
    assert not ReliabilityEvaluator(agent=_Crash(), input_text="q",
                                    forbidden_tools=["rm"]).run().passed
    assert not asyncio.run(
        ReliabilityEvaluator(agent=_Crash(), input_text="q").run_async()).passed
