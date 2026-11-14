"""Regression tests for #6319 (part b): failed BackgroundTask.wait() and
ReliabilityEvaluator stale/crashed runs."""
import asyncio

import pytest

from praisonaiagents.background import BackgroundRunner
from praisonaiagents.eval.reliability import ReliabilityEvaluator


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


class _Rewriter:
    """chat() replaces history with an equal-length new history."""

    def __init__(self):
        self.chat_history = [{"role": "user", "content": str(i)} for i in range(2)]

    def chat(self, q):
        self.chat_history = [{"role": "user", "content": q},
                             {"role": "tool", "name": "rm"}]
        return "x"


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


def test_reliability_rewritten_history_detects_new_calls():
    assert not ReliabilityEvaluator(agent=_Rewriter(), input_text="q",
                                    forbidden_tools=["rm"]).run().passed


class _Resumed:
    """Saved history is restored lazily on the first chat() (resumed session)."""

    def __init__(self):
        self.chat_history = []
        self._loaded = False

    def _init_session_store(self):
        if not self._loaded:
            self._loaded = True
            self.chat_history.append({"role": "tool", "name": "search"})

    def chat(self, q):
        self._init_session_store()
        self.chat_history.append({"role": "assistant", "content": "x"})
        return "x"


def test_reliability_ignores_lazily_restored_session_history():
    assert not ReliabilityEvaluator(agent=_Resumed(), input_text="q",
                                    expected_tools=["search"]).run().passed
    assert ReliabilityEvaluator(agent=_Resumed(), input_text="q",
                                forbidden_tools=["search"]).run().passed
