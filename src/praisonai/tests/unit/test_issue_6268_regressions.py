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


# --- 2. serve agents never echoes internal exception text --------------------

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from praisonai.cli.features.serve import ServeHandler, _MAX_QUERY_CHARS  # noqa: E402

SECRET = "/etc/secret/path sk-leaked"


@pytest.fixture
def agents_file(tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text("framework: praisonai\nroles: {}\n")
    return str(path)


@pytest.fixture
def boom_arun(monkeypatch):
    import praisonai

    async def _boom(**kwargs):
        raise RuntimeError(SECRET)

    monkeypatch.setattr(praisonai, "arun", _boom, raising=False)


def _apps(agents_file):
    handler = ServeHandler()
    cfg = {"host": "127.0.0.1", "port": 8765, "file": agents_file}
    agents_app = handler._create_agents_app({**cfg, "path": "/agents"})
    unified_app = handler._create_unified_app(cfg)
    return [(agents_app, "/agents"), (agents_app, "/agents/x"), (unified_app, "/agents")]


def test_agent_failure_does_not_leak_exception_text(agents_file, boom_arun):
    for app, route in _apps(agents_file):
        resp = TestClient(app).post(route, json={"query": "hi"})
        assert resp.status_code == 500, route
        assert SECRET not in resp.text, route
        body = resp.json()
        assert body["error"] == "Internal server error"
        assert body["error_id"]


def test_oversize_query_is_rejected(agents_file, boom_arun):
    big = "x" * (_MAX_QUERY_CHARS + 1)
    for app, route in _apps(agents_file):
        resp = TestClient(app).post(route, json={"message": big})
        assert resp.status_code in (413, 422), route
