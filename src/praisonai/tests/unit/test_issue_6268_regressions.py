"""Regression tests for issue #6268."""

import sys
import types
from unittest import mock

import pytest


# --- 1. CrewAI agents receive crewai.LLM (model name preserved) -------------

class _FakeLLM:
    def __init__(self, model, base_url=None, api_key=None):
        self.model, self.base_url, self.api_key = model, base_url, api_key


def test_crewai_agent_llm_is_crewai_llm(monkeypatch):
    built = []

    class _Agent:
        def __init__(self, **kw):
            built.append(kw)

    fake = types.ModuleType("crewai")
    fake.LLM = _FakeLLM
    fake.Agent = _Agent
    fake.Task = mock.MagicMock()
    fake.Crew = mock.MagicMock()
    fake.Process = types.SimpleNamespace(hierarchical="hierarchical")
    telemetry = types.ModuleType("crewai.telemetry")
    telemetry.Telemetry = type("Telemetry", (), {})
    fake.telemetry = telemetry
    monkeypatch.setitem(sys.modules, "crewai", fake)
    monkeypatch.setitem(sys.modules, "crewai.telemetry", telemetry)

    from praisonai.framework_adapters.crewai_adapter import CrewAIAdapter

    config = {"roles": {"writer": {
        "role": "Writer", "goal": "g", "backstory": "b",
        "llm": {"model": "anthropic/claude-x", "base_url": "http://h", "api_key": "k"},
        "tasks": {"t": {"description": "d", "expected_output": "o"}},
    }}}
    CrewAIAdapter()._build_crew(config, [], "topic")

    kw = built[0]
    assert isinstance(kw["llm"], _FakeLLM)
    assert (kw["llm"].model, kw["llm"].base_url, kw["llm"].api_key) == (
        "anthropic/claude-x", "http://h", "k",
    )
    # Unset function_calling_llm defers to the agent llm instead of a bogus client.
    assert kw["function_calling_llm"] is None
