"""A tool that raises must give the same outcome via chat() and achat() (#6041).

Contract: a *raised* tool exception ends the turn with ToolExecutionError on
both paths. A tool that *returns* ``{"error": ...}`` stays a recoverable tool
result the model sees.
"""
import asyncio
import json

import pytest

from praisonaiagents import Agent
from praisonaiagents.errors import ToolExecutionError

from tests.unit.agent.test_tool_failure_not_relabelled import (
    _agent_with_failing_tool,
)


# --- OpenAI-native path -----------------------------------------------------

def test_native_chat_and_achat_both_raise(monkeypatch):
    monkeypatch.setattr("asyncio.sleep", _no_sleep)
    agent, _rec, runs = _agent_with_failing_tool("smtp down", monkeypatch)
    with pytest.raises(ToolExecutionError):
        agent.chat("send the email")
    assert runs

    agent, _rec, runs = _agent_with_failing_tool("smtp down", monkeypatch)
    with pytest.raises(ToolExecutionError):
        asyncio.run(agent.achat("send the email"))
    assert runs


# --- provider (litellm) path ------------------------------------------------

async def _no_sleep(*_a, **_k):
    return None


def _stub_litellm(monkeypatch, seen):
    litellm = pytest.importorskip("litellm")
    from litellm import ModelResponse

    def fake_completion(*_a, **k):
        tool_msgs = [m for m in k["messages"] if m.get("role") == "tool"]
        if not tool_msgs:
            msg = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "send_email",
                             "arguments": json.dumps({"to": "a@b.c"})}}]}
            fr = "tool_calls"
        else:
            seen.append(tool_msgs[-1]["content"])
            msg = {"role": "assistant", "content": "the email could not be sent"}
            fr = "stop"
        return ModelResponse(
            choices=[{"index": 0, "finish_reason": fr, "message": msg}],
            usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        )

    async def fake_acompletion(*a, **k):
        return fake_completion(*a, **k)

    def _blocked(*_a, **_k):
        raise RuntimeError("network blocked in test")

    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    monkeypatch.setattr(litellm, "responses", _blocked, raising=False)
    monkeypatch.setattr(litellm, "aresponses", _blocked, raising=False)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    monkeypatch.setattr("asyncio.sleep", _no_sleep)


def _provider_agent(tool):
    return Agent(name="m", instructions="x",
                 llm="anthropic/claude-3-5-sonnet-20240620",
                 tools=[tool], output="silent")


def _outcome(call):
    try:
        return ("returned", call())
    except ToolExecutionError:
        return ("raised", None)


def test_provider_raised_tool_exception_same_outcome(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    seen = []
    _stub_litellm(monkeypatch, seen)

    def send_email(to: str) -> str:
        """Send an email."""
        raise RuntimeError("SMTP server unreachable")

    sync = _outcome(lambda: _provider_agent(send_email).chat("email a@b.c"))
    async_ = _outcome(
        lambda: asyncio.run(_provider_agent(send_email).achat("email a@b.c"))
    )
    assert sync[0] == async_[0] == "raised"
    assert seen == []


def test_provider_returned_error_dict_reaches_model_on_both(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    seen = []
    _stub_litellm(monkeypatch, seen)

    def send_email(to: str) -> dict:
        """Send an email."""
        return {"error": "mailbox full"}

    sync = _outcome(lambda: _provider_agent(send_email).chat("email a@b.c"))
    assert sync == ("returned", "the email could not be sent")
    assert seen and all("mailbox full" in m for m in seen)

    seen.clear()
    async_ = _outcome(
        lambda: asyncio.run(_provider_agent(send_email).achat("email a@b.c"))
    )
    assert async_ == ("returned", "the email could not be sent")
    assert seen and all("mailbox full" in m for m in seen)


def test_provider_not_restart_safe_raise_is_not_retryable(monkeypatch):
    # A restart_safe=False tool must not run again, so the error must not
    # advertise a retry (durable runs would otherwise stay open).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    seen = []
    _stub_litellm(monkeypatch, seen)
    runs = []

    def send_email(to: str) -> str:
        """Send an email."""
        runs.append(to)
        raise RuntimeError("SMTP server unreachable")
    send_email.restart_safe = False

    with pytest.raises(ToolExecutionError) as exc:
        asyncio.run(_provider_agent(send_email).achat("email a@b.c"))
    assert exc.value.is_retryable is False
    assert runs == ["a@b.c"]
    assert seen == []
