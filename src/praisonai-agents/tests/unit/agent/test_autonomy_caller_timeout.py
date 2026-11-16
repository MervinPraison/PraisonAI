"""Caller-mode autonomy must accept ``timeout`` (Issue #6044).

``Agent(autonomy=...).start(prompt, timeout=...)`` used to forward ``timeout``
to ``chat()``/``achat()``, which do not accept it -> TypeError before any LLM
call. The timeout is now consumed and enforced as a run budget.
"""
import asyncio
import time

import pytest

from praisonaiagents import Agent


def _agent():
    return Agent(name="t", instructions="x", autonomy={"level": "suggest"}, output="silent")


@pytest.mark.parametrize("timeout", [None, 5])
def test_start_caller_mode_accepts_timeout(timeout):
    agent = _agent()
    seen = {}

    def fake_chat(prompt, **kwargs):
        seen.update(kwargs)
        return "ok"

    agent.chat = fake_chat
    result = agent.start("x", timeout=timeout)
    assert result.success is True
    assert result.completion_reason == "caller_mode"
    assert "timeout" not in seen


def test_start_caller_mode_enforces_timeout():
    agent = _agent()

    def slow_chat(prompt, cancel_token=None, **kwargs):
        deadline = time.time() + 5
        while time.time() < deadline:
            if cancel_token is not None and cancel_token.is_set():
                raise InterruptedError("cancelled")
            time.sleep(0.01)
        return "too late"

    agent.chat = slow_chat
    started = time.time()
    result = agent.start("x", timeout=0.1)
    assert time.time() - started < 2
    assert result.success is False
    assert result.completion_reason == "timeout"


def test_start_caller_mode_timeout_interrupt_text_is_not_success():
    """The LLM tool loop returns this text instead of raising on cancel."""
    agent = _agent()

    def interrupted_chat(prompt, cancel_token=None, **kwargs):
        while not cancel_token.is_set():
            time.sleep(0.01)
        return f"Task interrupted: {cancel_token.reason}"

    agent.chat = interrupted_chat
    result = agent.start("x", timeout=0.1)
    assert result.success is False
    assert result.completion_reason == "timeout"


def test_start_caller_mode_timeout_keeps_interrupt_controller():
    """A positive timeout must not hide stop requests on the agent's controller."""
    from praisonaiagents.agent.interrupt import InterruptController

    agent = _agent()
    agent.interrupt_controller = InterruptController()
    agent.interrupt_controller.request("user")  # stop requested before the run

    def chat(prompt, cancel_token=None, **kwargs):
        cancel_token.check()
        return "ran anyway"

    agent.chat = chat
    started = time.time()
    with pytest.raises(InterruptedError, match="user"):
        agent.start("x", timeout=5)
    assert time.time() - started < 2


@pytest.mark.parametrize("timeout", [None, 5])
def test_astart_caller_mode_accepts_timeout(timeout):
    agent = _agent()
    seen = {}

    async def fake_achat(prompt, **kwargs):
        seen.update(kwargs)
        return "ok"

    agent.achat = fake_achat
    result = asyncio.run(agent.astart("x", timeout=timeout))
    assert result.success is True
    assert result.completion_reason == "caller_mode"
    assert "timeout" not in seen


def test_astart_caller_mode_enforces_timeout():
    agent = _agent()

    async def slow_achat(prompt, **kwargs):
        await asyncio.sleep(5)
        return "too late"

    agent.achat = slow_achat
    started = time.time()
    result = asyncio.run(agent.astart("x", timeout=0.1))
    assert time.time() - started < 2
    assert result.success is False
    assert result.completion_reason == "timeout"


def test_start_caller_mode_interrupt_text_without_timeout_is_success():
    """A completed answer that merely quotes the interrupt text stays a success."""
    agent = _agent()
    agent.chat = lambda prompt, **kwargs: "Task interrupted: timeout (quoted)"
    result = agent.start("x", timeout=5)
    assert result.success is True
    assert result.completion_reason == "caller_mode"


def test_astart_caller_mode_timeout_waits_for_achat_cleanup():
    agent = _agent()
    cleaned = []

    async def slow_achat(prompt, **kwargs):
        try:
            await asyncio.sleep(5)
        finally:
            await asyncio.sleep(0.05)
            cleaned.append(True)

    agent.achat = slow_achat
    result = asyncio.run(agent.astart("x", timeout=0.1))
    assert result.completion_reason == "timeout"
    assert cleaned == [True]
