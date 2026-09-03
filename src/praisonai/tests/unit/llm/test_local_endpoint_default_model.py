"""Pointing at a local endpoint without naming a model must say so.

The README's local-model recipe was `export OPENAI_BASE_URL=http://localhost:11434/v1`
and nothing else. With no model named, the agent falls back to OpenAI's default,
`gpt-4o-mini`, and sends that name to Ollama:

    404 - model 'gpt-4o-mini' not found

which reads like a bug in the SDK rather than a missing line in the user's
config. This adds a one-time warning naming the variable to set.

Deliberately a warning, not an error: an OpenAI-compatible proxy (LiteLLM,
vLLM's OpenAI server) may legitimately serve `gpt-4o-mini` under that exact
name, and raising would break those users.

Constructed state only: no network, no server.
"""

import logging

import pytest

from praisonaiagents import Agent
from praisonaiagents.agent import agent as agent_module

LOCAL_URL = "http://localhost:11434/v1"

_VARS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GROQ_API_KEY", "COHERE_API_KEY", "OLLAMA_HOST", "OPENAI_MODEL_NAME",
    "OPENAI_BASE_URL", "OPENAI_API_BASE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(Agent, "_default_model_checked", False, raising=False)
    monkeypatch.setattr(Agent, "_default_model", None, raising=False)
    # The notice fires once per process; reset it so each test sees a clean slate.
    monkeypatch.setattr(agent_module, "_LOCAL_ENDPOINT_DEFAULT_MODEL_WARNED", False, raising=False)
    yield
    monkeypatch.setattr(Agent, "_default_model_checked", False, raising=False)


@pytest.mark.parametrize("env_var", ["OPENAI_BASE_URL", "OPENAI_API_BASE"])
def test_warns_when_local_endpoint_has_no_model(monkeypatch, caplog, env_var):
    monkeypatch.setenv(env_var, LOCAL_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with caplog.at_level(logging.WARNING):
        Agent(instructions="test")

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert "OPENAI_MODEL_NAME" in joined, (
        f"no actionable warning was emitted; got: {joined!r}"
    )
    assert "gpt-4o-mini" in joined


def test_warning_fires_only_once(monkeypatch, caplog):
    """A loop building many agents must not produce a wall of identical text."""
    monkeypatch.setenv("OPENAI_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            Agent(instructions="test")

    hits = [r for r in caplog.records if "OPENAI_MODEL_NAME" in r.getMessage()]
    assert len(hits) == 1, f"expected one notice, got {len(hits)}"


def test_no_warning_when_model_is_named(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("OPENAI_MODEL_NAME", "qwen3:0.6b")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with caplog.at_level(logging.WARNING):
        Agent(instructions="test")

    assert not [r for r in caplog.records if "OPENAI_MODEL_NAME" in r.getMessage()]


def test_no_warning_when_llm_passed_explicitly(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with caplog.at_level(logging.WARNING):
        Agent(instructions="test", llm="ollama/qwen3:0.6b")

    assert not [r for r in caplog.records if "OPENAI_MODEL_NAME" in r.getMessage()]


def test_no_warning_for_real_openai(monkeypatch, caplog):
    """The default model is correct against api.openai.com; stay quiet."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with caplog.at_level(logging.WARNING):
        Agent(instructions="test")

    assert not [r for r in caplog.records if "OPENAI_MODEL_NAME" in r.getMessage()]


def test_no_warning_when_provider_credential_resolves_prefixed_model(monkeypatch, caplog):
    """A provider credential (e.g. OLLAMA_HOST) resolves an already-correct
    provider-prefixed default, so the OpenAI-default warning must stay quiet and
    must not mislabel that model as ``gpt-4o-mini``."""
    monkeypatch.setenv("OPENAI_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("OLLAMA_HOST", "http://localhost:11434")

    with caplog.at_level(logging.WARNING):
        Agent(instructions="test")

    assert not [r for r in caplog.records if "OPENAI_MODEL_NAME" in r.getMessage()]


def test_warns_when_only_api_base_is_set(monkeypatch, caplog):
    """The client reads OPENAI_API_BASE first; the message must name it."""
    monkeypatch.setenv("OPENAI_API_BASE", LOCAL_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with caplog.at_level(logging.WARNING):
        Agent(instructions="test")

    joined = " ".join(r.getMessage() for r in caplog.records)
    assert LOCAL_URL in joined, f"warning did not name the endpoint; got: {joined!r}"


def test_no_warning_without_any_base_url(monkeypatch, caplog):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with caplog.at_level(logging.WARNING):
        Agent(instructions="test")

    assert not [r for r in caplog.records if "OPENAI_MODEL_NAME" in r.getMessage()]


def test_warning_does_not_change_routing(monkeypatch):
    """This is a diagnostic only. A proxy serving gpt-4o-mini must still work."""
    monkeypatch.setenv("OPENAI_BASE_URL", LOCAL_URL)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    agent = Agent(instructions="test")

    assert agent.llm == "gpt-4o-mini"
    assert agent._using_custom_llm is False
