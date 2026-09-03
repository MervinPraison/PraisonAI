"""`Agent(llm="local")` resolves a running local server, and nothing else probes.

The opt-in guarantee matters as much as the feature: discovery must never fire
for a spec that is not "local", so a fully-configured agent pays nothing for this
existing.
"""

import pytest

from praisonaiagents import Agent
from praisonaiagents.local import LocalEngine, NoLocalEngineError

from .conftest import Recorder, ok, text

pytestmark = pytest.mark.unit

ROUTES = {
    ("GET", "/"): text("Ollama is running"),
    ("GET", "/api/version"): ok({"version": "0.33.2"}),
    ("GET", "/api/tags"): ok({"models": [
        {"model": "qwen3:0.6b", "capabilities": ["completion", "tools"],
         "modified_at": "2026-09-03T13:44:23Z"}]}),
    ("POST", "/api/show"): ok({"capabilities": ["completion", "tools"]}),
}


@pytest.fixture
def local_server(monkeypatch):
    """Point the resolver's default transport at a canned Ollama."""
    # `import praisonaiagents.local.discover` binds the re-exported *function*
    # of that name, not the module, so reach for the module explicitly.
    import importlib
    discover_mod = importlib.import_module("praisonaiagents.local.discover")
    resolve_mod = importlib.import_module("praisonaiagents.local.resolve")
    rec = Recorder(ROUTES)
    monkeypatch.setattr(discover_mod, "default_transport", rec)
    monkeypatch.setattr(resolve_mod, "default_transport", rec)
    return rec


def test_agent_llm_local_resolves(local_server):
    agent = Agent(instructions="test", llm="local")
    assert agent.llm == "ollama/qwen3:0.6b"
    assert agent._using_custom_llm is True
    assert agent._local_target.engine is LocalEngine.OLLAMA


def test_agent_llm_local_sets_base_url_and_key(local_server):
    agent = Agent(instructions="test", llm="local")
    assert agent.llm_instance.base_url == "http://127.0.0.1:11434"
    # openai clients reject an empty key; the placeholder must be non-empty.
    assert agent.llm_instance.api_key


def test_agent_local_with_engine_spec(local_server):
    agent = Agent(instructions="test", llm="local:ollama/qwen3:0.6b")
    assert agent.llm == "ollama/qwen3:0.6b"


def test_explicit_base_url_is_not_overridden(local_server):
    agent = Agent(instructions="test", llm="local", base_url="http://example:1234")
    assert agent.llm_instance.base_url == "http://example:1234"


def test_nothing_running_raises_a_named_error(monkeypatch):
    # `import praisonaiagents.local.discover` binds the re-exported *function*
    # of that name, not the module, so reach for the module explicitly.
    import importlib
    discover_mod = importlib.import_module("praisonaiagents.local.discover")
    resolve_mod = importlib.import_module("praisonaiagents.local.resolve")
    empty = Recorder({})
    monkeypatch.setattr(discover_mod, "default_transport", empty)
    monkeypatch.setattr(resolve_mod, "default_transport", empty)
    with pytest.raises(NoLocalEngineError):
        Agent(instructions="test", llm="local")


@pytest.mark.parametrize("spec", ["gpt-4o", "ollama/llama3.2", "anthropic/claude-3-5-sonnet-latest"])
def test_other_specs_never_probe(monkeypatch, spec):
    """Safe defaults: discovery is opt-in and must not fire for anything else."""
    # `import praisonaiagents.local.discover` binds the re-exported *function*
    # of that name, not the module, so reach for the module explicitly.
    import importlib
    discover_mod = importlib.import_module("praisonaiagents.local.discover")
    resolve_mod = importlib.import_module("praisonaiagents.local.resolve")
    tripwire = Recorder({})
    monkeypatch.setattr(discover_mod, "default_transport", tripwire)
    monkeypatch.setattr(resolve_mod, "default_transport", tripwire)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    Agent(instructions="test", llm=spec)
    assert tripwire.calls == [], f"{spec!r} triggered discovery: {tripwire.calls}"
