"""run_autonomous() and run_autonomous_async() behave the same (G-17 pair 2, step 1).

Pins what both entry points do today, so the later merge (the sync method
running the async one) has to keep it. The model is stubbed; no network.
"""

import asyncio

import pytest

from praisonaiagents import Agent
from praisonaiagents import main as display


@pytest.fixture
def events(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    seen = []
    for name in ("autonomy_iteration", "autonomy_complete", "autonomy_doom_loop"):
        monkeypatch.setitem(display.sync_display_callbacks, name,
                            (lambda n: (lambda **kw: seen.append((n, kw.get("completion_reason") or kw.get("stage")))))(name))
    return seen


def _run(mode, reply):
    agent = Agent(name="a", instructions="hi", autonomy=True)
    if mode == "sync":
        agent.chat = lambda prompt, **kw: reply(prompt)
        return agent, agent.run_autonomous("do x", max_iterations=3)

    async def achat(prompt, **kw):
        return reply(prompt)

    agent.achat = achat
    return agent, asyncio.run(agent.run_autonomous_async("do x", max_iterations=3))


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_completion(events, mode):
    _, r = _run(mode, lambda p: "Task completed. TASK_COMPLETE")
    assert (r.success, r.completion_reason, r.iterations) == (True, "goal", 1)
    assert r.output == "Task completed. TASK_COMPLETE"
    assert events == [("autonomy_iteration", "direct"), ("autonomy_complete", "goal")]


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_plain_reply_counts_as_goal_today(events, mode):
    # Both sides treat a plain reply as the goal on the first turn.
    _, r = _run(mode, lambda p: "still working on step 1")
    assert (r.success, r.completion_reason, r.iterations) == (True, "goal", 1)


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_model_error(events, mode):
    def boom(p):
        raise RuntimeError("model down")
    _, r = _run(mode, boom)
    assert (r.success, r.completion_reason, r.iterations) == (False, "error", 1)
    assert r.error == "model down" and r.output == "model down"


def test_ctrl_c_on_sync_returns_a_cancelled_result(events):
    def ctrl_c(p):
        raise KeyboardInterrupt
    _, r = _run("sync", ctrl_c)
    assert (r.success, r.completion_reason, r.output) == (False, "cancelled", "Task cancelled by user")
    assert events == [("autonomy_iteration", "direct")]


def test_keyboard_interrupt_on_async_returns_a_cancelled_result(events):
    def ctrl_c(p):
        raise KeyboardInterrupt
    _, r = _run("async", ctrl_c)
    assert (r.success, r.completion_reason, r.output) == (False, "cancelled", "Task cancelled")


def test_task_cancel_on_async_reraises_and_keeps_the_partial_result(events):
    agent = Agent(name="a", instructions="hi", autonomy=True)

    async def achat(prompt, **kw):
        raise asyncio.CancelledError

    agent.achat = achat
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(agent.run_autonomous_async("do x", max_iterations=3))
    partial = agent._last_autonomy_result
    assert (partial.success, partial.completion_reason, partial.output) == (False, "cancelled", "Task cancelled")
