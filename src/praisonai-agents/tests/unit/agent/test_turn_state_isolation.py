"""Per-turn state regressions (issue #5763).

1. The loop guard is reset at the start of every chat turn, so per-turn limits
   do not accumulate over the life of a long-lived agent.
2. A terminal LLM failure is reported via ``last_stop_reason == "error"``.
3. Each concurrent turn's tools/approvals see their own cancel token.
"""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest


def _agent(monkeypatch):
    from praisonaiagents import Agent

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    agent = Agent(name="turn-state", instructions="Test", llm="gpt-4o-mini")
    agent._using_custom_llm = False
    monkeypatch.setattr(agent, "_execute_callback_and_display", MagicMock())
    monkeypatch.setattr(agent, "_persist_message", MagicMock())
    return agent


def _impl_kwargs():
    return dict(
        temperature=1.0, tools=None, output_json=None, output_pydantic=None,
        reasoning_steps=False, stream=False, task_name=None, task_description=None,
        task_id=None, config=None, force_retrieval=False, skip_retrieval=True,
        attachments=None, _trace_emitter=MagicMock(),
    )


def _boom(*args, **kwargs):
    raise RuntimeError("Error code: 500")


def test_chat_resets_loop_guard_each_turn(monkeypatch):
    agent = _agent(monkeypatch)
    guard = agent._ensure_loop_guard()
    for _ in range(5):
        guard.record("lookup", {"q": "x"}, True, "same")
    guard._turn_start_time = 0.0  # a turn clock started long ago
    monkeypatch.setattr(agent, "_chat_completion", _boom)

    agent._chat_impl(prompt="hi", **_impl_kwargs())

    assert guard._tool_counts == {}
    assert guard._turn_start_time > 0.0
    assert guard.check("lookup", {"q": "y"}).action.value == "allow"


def test_chat_does_not_create_loop_guard(monkeypatch):
    agent = _agent(monkeypatch)
    monkeypatch.setattr(agent, "_chat_completion", _boom)
    agent._chat_impl(prompt="hi", **_impl_kwargs())
    assert agent._loop_guard is None


def test_sync_llm_failure_sets_error_stop_reason(monkeypatch):
    agent = _agent(monkeypatch)
    monkeypatch.setattr(agent, "_chat_completion", _boom)

    assert agent._chat_impl(prompt="hi", **_impl_kwargs()) is None
    assert agent.last_stop_reason == "error"


def test_async_llm_failure_sets_error_stop_reason(monkeypatch):
    agent = _agent(monkeypatch)

    async def aboom(*args, **kwargs):
        raise RuntimeError("Error code: 500")

    monkeypatch.setattr(agent, "_achat_completion", aboom, raising=False)
    monkeypatch.setattr(agent, "_achat_completion_with_retry_core", aboom, raising=False)
    kwargs = _impl_kwargs()
    assert asyncio.run(agent._achat_impl(prompt="hi", **kwargs)) is None
    assert agent.last_stop_reason == "error"


def test_error_stop_reason_does_not_leak_into_next_turn(monkeypatch):
    agent = _agent(monkeypatch)
    agent._last_stop_reason = "error"
    monkeypatch.setattr(agent, "_chat_completion", _boom)
    # Turn start clears the previous turn's classification before any work.
    monkeypatch.setattr(agent, "_build_messages", MagicMock(side_effect=KeyError))
    with pytest.raises(KeyError):
        agent._chat_impl(prompt="hi", **_impl_kwargs())
    assert agent._last_stop_reason == "completed"


def test_concurrent_turns_see_their_own_cancel_token(monkeypatch):
    agent = _agent(monkeypatch)
    started_a = threading.Event()
    release_a = threading.Event()
    seen = {}

    class _Tok:
        def __init__(self):
            self.cancelled = False

        def is_set(self):
            return self.cancelled

    tokens = {"A": _Tok(), "B": _Tok()}

    def fake_impl(prompt, *args, **kwargs):
        if prompt == "A":
            started_a.set()
            release_a.wait(5)
        seen[prompt] = agent._current_turn_liveness()
        return "ok"

    monkeypatch.setattr(agent, "_chat_impl", fake_impl)
    th = threading.Thread(target=agent.chat, args=("A",), kwargs={"cancel_token": tokens["A"]})
    th.start()
    assert started_a.wait(5)
    agent.chat("B", cancel_token=tokens["B"])  # B starts (and ends) while A is in flight
    release_a.set()
    th.join(5)

    tokens["B"].cancelled = True
    assert seen["A"]() is True  # cancelling B does not mark A stale
    assert seen["B"]() is False
    tokens["A"].cancelled = True
    assert seen["A"]() is False
