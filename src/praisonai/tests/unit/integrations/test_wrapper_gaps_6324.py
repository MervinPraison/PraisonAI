"""Regression tests for issue #6324 wrapper gaps."""

import asyncio
import contextvars

import pytest

from praisonai.integrations._managed_base import ManagedBackendBase

_CV = contextvars.ContextVar("issue_6324_cv", default=None)


class _Backend(ManagedBackendBase):
    def __init__(self):
        self.seen = []

    def _ensure_session(self):
        self.seen.append(("session", _CV.get()))
        return "s"

    def _iter_events(self, session_id, prompt):
        self.seen.append(("events", _CV.get()))
        yield "chunk"

    def sync_call(self, prompt, stream_live=False):
        return _CV.get()


def test_execute_in_executor_copies_contextvars():
    async def _go():
        _CV.set("tenant-a")
        b = _Backend()
        return await b._execute_in_executor(b.sync_call, "ping")

    assert asyncio.run(_go()) == "tenant-a"


def test_stream_producer_copies_contextvars():
    async def _go():
        _CV.set("tenant-b")
        b = _Backend()
        chunks = [c async for c in b.stream("ping")]
        return chunks, b.seen

    chunks, seen = asyncio.run(_go())
    assert chunks == ["chunk"]
    assert seen == [("session", "tenant-b"), ("events", "tenant-b")]


class _FakeRegistry:
    def __init__(self, backend_cls):
        self._cls = backend_cls

    def is_available(self, name):
        return True

    def resolve(self, name):
        return self._cls


def _patch_registry(monkeypatch, backend_cls):
    from praisonai.integrations import backend_registry

    monkeypatch.setattr(
        backend_registry, "get_backend_registry", lambda: _FakeRegistry(backend_cls)
    )


def test_hosted_agent_returns_anthropic_subclass_plugin(monkeypatch):
    from praisonai.integrations.hosted_agent import HostedAgent
    from praisonai.integrations.managed_agents import AnthropicManagedAgent

    class AcmeHostedAgent(AnthropicManagedAgent):
        def marker(self):
            return "acme"

    _patch_registry(monkeypatch, AcmeHostedAgent)
    agent = HostedAgent(provider="acme")
    assert type(agent) is AcmeHostedAgent
    assert agent.marker() == "acme"


def test_hosted_agent_returns_hosted_subclass_plugin(monkeypatch):
    from praisonai.integrations.hosted_agent import HostedAgent

    class AcmeHosted(HostedAgent):
        def marker(self):
            return "acme"

    _patch_registry(monkeypatch, AcmeHosted)
    agent = HostedAgent(provider="acme")
    assert type(agent) is AcmeHosted
    assert agent.marker() == "acme"
    assert agent.provider == "acme"  # __init__ ran


def test_hosted_agent_plugin_init_runs_exactly_once(monkeypatch):
    from praisonai.integrations.hosted_agent import HostedAgent

    calls = []

    class AcmeHosted(HostedAgent):
        def __init__(self, provider="acme", config=None, **kwargs):
            calls.append((provider, kwargs))
            super().__init__(provider=provider, config=config, **kwargs)

    _patch_registry(monkeypatch, AcmeHosted)
    agent = HostedAgent(provider="acme", api_key="k")
    assert type(agent) is AcmeHosted
    assert calls == [("acme", {"api_key": "k"})]


def test_hosted_agent_builtin_anthropic_still_hosted_agent():
    from praisonai.integrations.hosted_agent import HostedAgent

    assert type(HostedAgent(provider="anthropic")) is HostedAgent


@pytest.mark.parametrize("key", ["model", "llm"])
def test_run_model_kwarg_beats_yaml_llm(key):
    from praisonai._entrypoint import _apply_model_override, _merge_cli_config
    from praisonai.agents_generator import AgentsGenerator

    config_list = [{"model": "resolved"}]
    extra = {key: "python-model"}
    _apply_model_override(config_list, extra)
    cli_config = _merge_cli_config(None, extra)
    assert cli_config["model"] == "python-model"
    assert "llm" not in cli_config

    gen = AgentsGenerator.__new__(AgentsGenerator)
    gen.config_list = config_list
    gen.cli_config = cli_config
    out = gen._run_config_list({"llm": "yaml-model"})
    assert out[0]["model"] == "python-model"
