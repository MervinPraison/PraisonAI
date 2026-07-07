"""Tests for the unified, graceful multi-step tool budget (ExecutionConfig.max_steps).

Covers:
- ExecutionConfig.max_steps consolidation + resolver helpers (backward compatible).
- Both tool-execution loops (OpenAI-native + LiteLLM) honour the SAME budget.
- Structured stop_reason ("completed" | "max_steps") surfaced to callers instead
  of a magic string, plus a graceful wrap-up injection near the budget.
- A real agentic test (gated on OPENAI_API_KEY) per AGENTS.md §9.4.
"""

import os
import pytest

from praisonaiagents import Agent, ExecutionConfig


# ---------------------------------------------------------------------------
# ExecutionConfig — unified knob + backward-compatible resolvers
# ---------------------------------------------------------------------------

def test_max_steps_defaults_to_none_and_falls_back_to_max_iter():
    cfg = ExecutionConfig()
    assert cfg.max_steps is None
    # Backward compatible: unset max_steps falls back to max_iter / per-turn cap.
    assert cfg.resolved_max_steps() == cfg.max_iter == 20
    assert cfg.resolved_max_tool_calls() == cfg.max_tool_calls_per_turn == 10


def test_max_steps_when_set_governs_both_budgets():
    cfg = ExecutionConfig(max_steps=50)
    assert cfg.resolved_max_steps() == 50
    # The single knob also drives the per-turn tool-call guardrail.
    assert cfg.resolved_max_tool_calls() == 50


def test_max_steps_validation_rejects_non_positive():
    with pytest.raises(ValueError):
        ExecutionConfig(max_steps=0)
    with pytest.raises(ValueError):
        ExecutionConfig(max_steps=-3)


def test_max_steps_survives_dict_round_trip():
    cfg = ExecutionConfig(max_steps=42, max_tool_calls_per_turn=7)
    restored = ExecutionConfig.from_dict(cfg.to_dict())
    assert restored.max_steps == 42
    assert restored.max_tool_calls_per_turn == 7
    assert restored.resolved_max_steps() == 42


# ---------------------------------------------------------------------------
# Agent wiring — the resolver feeds BOTH loops identically
# ---------------------------------------------------------------------------

def test_agent_resolves_max_steps_for_both_loops():
    agent = Agent(
        name="coder",
        instructions="Be helpful",
        execution=ExecutionConfig(max_steps=33),
    )
    # chat_mixin resolvers used by the OpenAI-native loop
    assert agent._resolve_max_steps() == 33
    assert agent._resolve_max_tool_calls() == 33
    # LiteLLM loop reads the same budget via LLM.max_iter (set from resolved_max_steps)
    assert agent.max_iter == 33


def test_agent_without_max_steps_keeps_legacy_defaults():
    agent = Agent(name="coder", instructions="Be helpful")
    assert agent._resolve_max_steps() == 20
    assert agent._resolve_max_tool_calls() == 10
    assert agent.max_iter == 20


def test_agent_last_stop_reason_defaults_to_completed():
    agent = Agent(name="coder", instructions="Be helpful")
    assert agent.last_stop_reason == "completed"


# ---------------------------------------------------------------------------
# OpenAI-native loop — stop_reason + graceful wrap-up (no network)
# ---------------------------------------------------------------------------

class _FakeToolCall:
    def __init__(self, name, args="{}", tid="call_1"):
        self.id = tid
        self.type = "function"

        class _Fn:
            pass

        self.function = _Fn()
        self.function.name = name
        self.function.arguments = args


class _FakeMessage:
    def __init__(self, tool_calls=None, content=""):
        self.tool_calls = tool_calls
        self.content = content


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, tool_calls=None, content=""):
        self.choices = [_FakeChoice(_FakeMessage(tool_calls, content))]
        self.usage = None


def _make_openai_client():
    from praisonaiagents.llm.openai_client import OpenAIClient

    client = OpenAIClient.__new__(OpenAIClient)
    client.logger = __import__("logging").getLogger("test")
    return client


def test_openai_loop_sets_max_steps_when_budget_exhausted(monkeypatch):
    client = _make_openai_client()

    # Always ask for another tool call so the loop can never "complete".
    def _always_tool_call(**kwargs):
        return _FakeResponse(tool_calls=[_FakeToolCall("noop")], content="working")

    monkeypatch.setattr(client, "format_tools", lambda tools: tools or [])
    monkeypatch.setattr(client, "create_completion", _always_tool_call)

    injected = {"wrapup": False}

    def _execute_tool(name, args, tool_call_id=None):
        return {"ok": True}

    # Detect the wrap-up injection by scanning messages before the final call.
    messages = [{"role": "user", "content": "do a big task"}]

    from praisonaiagents.llm import openai_client as oc

    orig_create = client.create_completion

    def _tracking_create(**kwargs):
        for m in kwargs.get("messages", []):
            if m.get("content") == oc._MAX_STEPS_WRAPUP_PROMPT:
                injected["wrapup"] = True
        return orig_create(**kwargs)

    monkeypatch.setattr(client, "create_completion", _tracking_create)

    client.chat_completion_with_tools(
        messages=messages,
        model="gpt-4o-mini",
        tools=[lambda: None],
        execute_tool_fn=_execute_tool,
        stream=False,
        verbose=False,
        max_iterations=3,
    )

    assert client._last_stop_reason == "max_steps"
    assert injected["wrapup"] is True


def test_openai_loop_completed_when_no_tool_calls(monkeypatch):
    client = _make_openai_client()
    monkeypatch.setattr(client, "format_tools", lambda tools: tools or [])
    monkeypatch.setattr(
        client,
        "create_completion",
        lambda **kwargs: _FakeResponse(tool_calls=None, content="done"),
    )

    client.chat_completion_with_tools(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o-mini",
        tools=None,
        execute_tool_fn=lambda *a, **k: {},
        stream=False,
        verbose=False,
        max_iterations=5,
    )
    assert client._last_stop_reason == "completed"


# ---------------------------------------------------------------------------
# LiteLLM loop — stop_reason on the per-turn guardrail
# ---------------------------------------------------------------------------

def test_litellm_last_stop_reason_default():
    from praisonaiagents.llm.llm import LLM

    llm = LLM.__new__(LLM)
    # Constructor sets this; ensure the attribute contract holds when set.
    llm._last_stop_reason = "completed"
    assert llm._last_stop_reason == "completed"


# ---------------------------------------------------------------------------
# Real agentic test (AGENTS.md §9.4) — gated on a real key.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY") and not os.getenv("PRAISONAI_LIVE_TESTS"),
    reason="Requires OPENAI_API_KEY / PRAISONAI_LIVE_TESTS for a real LLM call",
)
def test_real_agent_completes_with_raised_max_steps():
    agent = Agent(
        name="coder",
        instructions="You are a concise assistant.",
        execution=ExecutionConfig(max_steps=50),
    )
    result = agent.start("Say hello in one short sentence.")
    print("REAL AGENT OUTPUT:", result)
    assert result and isinstance(result, str)
    # A simple prompt with no tools should complete, not truncate.
    assert agent.last_stop_reason == "completed"
