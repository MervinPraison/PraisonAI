"""T-05 step 2c: pin what llm="local" does in Agent.__init__ before that block
moves out: the resolved model and endpoint, and keeping embeddings local
(pick a served embedding model, carry its width, warn when none is served).
Values recorded on main 33d767a0ce; no network (resolve and discovery faked).
"""
import logging
import types

import pytest

import praisonaiagents.local as local
from praisonaiagents import Agent

ROOT = "http://127.0.0.1:11434"


@pytest.fixture
def local_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def setup(models, engine=local.LocalEngine.OLLAMA):
        target = types.SimpleNamespace(
            litellm_model="ollama/llama3", base_url=ROOT, openai_base_url=ROOT + "/v1",
            api_key="local-key", engine=engine)
        monkeypatch.setattr(local, "resolve", lambda spec=None: target)
        monkeypatch.setattr(Agent, "_local_discovery", staticmethod(
            lambda t: types.SimpleNamespace(models=models, model_meta=())))
        return target
    return setup


def _warned(caplog):
    return [r for r in caplog.records if "resolved a local model, but" in r.getMessage()]


def test_ollama_target_uses_the_server_root(local_env):
    target = local_env(["llama3"])
    agent = Agent(name="a", instructions="hi", llm="local")
    assert agent._local_target is target
    assert (agent.llm_instance.model, agent.llm_instance.base_url) == ("ollama/llama3", ROOT)


def test_explicit_base_url_wins(local_env):
    local_env(["llama3"])
    agent = Agent(name="a", instructions="hi", llm="local", base_url="http://other/v1")
    assert agent.llm_instance.base_url == "http://other/v1"


def test_memory_gets_the_served_embedding_model(local_env, caplog):
    local_env(["llama3", "nomic-embed-text"])
    with caplog.at_level(logging.WARNING):
        agent = Agent(name="a", instructions="hi", llm="local", memory=True)
    assert agent.embedder_config == {"provider": "ollama", "config": {
        "model": "nomic-embed-text", "ollama_base_url": ROOT, "embedding_dims": 768}}
    assert not _warned(caplog)


def test_memory_without_an_embedding_model_warns(local_env, caplog):
    local_env(["llama3"])
    with caplog.at_level(logging.WARNING):
        agent = Agent(name="a", instructions="hi", llm="local", memory=True)
    assert agent.embedder_config is None
    assert len(_warned(caplog)) == 1


def test_no_memory_or_knowledge_means_no_embedder_and_no_warning(local_env, caplog):
    local_env(["llama3", "nomic-embed-text"])
    with caplog.at_level(logging.WARNING):
        agent = Agent(name="a", instructions="hi", llm="local")
    assert agent.embedder_config is None
    assert not _warned(caplog)
