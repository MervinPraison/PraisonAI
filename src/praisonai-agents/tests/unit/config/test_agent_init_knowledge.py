"""G-19: the knowledge= block of Agent.__init__ as a pure function.

Expected values were measured on main before the move.
"""
import pytest

from praisonaiagents import Agent
from praisonaiagents.config.agent_init import resolve_agent_knowledge
from praisonaiagents.config.feature_configs import KnowledgeConfig


class _LiveKnowledge:
    def search(self, *a, **k):
        return []

    def add(self, *a, **k):
        return None


def _kc():
    return KnowledgeConfig(
        sources=["a.txt"], retrieval_k=7, embedder="gemini", config={"top_k": 9},
        vector_store={"provider": "chroma",
                      "config": {"collection_name": "c", "path": "/p", "x": 1}},
    )


@pytest.mark.parametrize("value", [None, False])
def test_no_knowledge(value):
    assert resolve_agent_knowledge(value, None) == (None, None, None, None)


def test_true_and_list():
    cfg, knowledge, rc, emb = resolve_agent_knowledge(True, None)
    assert isinstance(cfg, KnowledgeConfig) and knowledge is None and rc["top_k"] == cfg.retrieval_k
    cfg, knowledge, rc, _ = resolve_agent_knowledge(["a.txt"], None)
    assert cfg.sources == ["a.txt"] and knowledge == ["a.txt"] and rc["enabled"] == cfg.auto_retrieve


def test_live_instance_passes_through():
    live = _LiveKnowledge()
    assert resolve_agent_knowledge(live, None) == (live, live, None, None)


def test_config_is_mapped_into_the_retrieval_dict():
    kc = _kc()
    cfg, knowledge, rc, emb = resolve_agent_knowledge(kc, None)
    assert cfg is kc and knowledge == ["a.txt"] and emb is None
    assert rc["top_k"] == 9, "config= overrides retrieval_k"
    assert (rc["vector_store_provider"], rc["collection_name"], rc["persist_path"],
            rc["vector_store_config"], rc["embedder_provider"]) == ("chroma", "c", "/p", {"x": 1}, "gemini")
    assert kc.vector_store["config"] == {"collection_name": "c", "path": "/p", "x": 1}, "input not mutated"


def test_user_retrieval_config():
    _, _, rc, _ = resolve_agent_knowledge(_kc(), {"top_k": 3, "citations": False})
    assert rc["top_k"] == 3 and rc["citations"] is False
    marker = object()
    assert resolve_agent_knowledge(None, marker)[2] is marker


def test_agent_receives_the_resolved_retrieval_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    agent = Agent(name="a", instructions="x", knowledge=_kc())
    rc = agent._retrieval_config
    assert (rc.top_k, rc.collection_name, rc.persist_path, rc.vector_store_config,
            rc.embedder_provider) == (9, "c", "/p", {"x": 1}, "gemini")
    assert Agent(name="a", instructions="x", knowledge=None)._knowledge_config is None
