"""Every declared KnowledgeConfig field must reach the internal config.

Regression tests for chunk_size / chunk_overlap / chunking_strategy / chunker /
vector_store / auto_retrieve / rerank_model / retrieval_threshold being inert,
and for config={...} wiping retrieval_k.
"""
import pytest

from praisonaiagents import Agent, KnowledgeConfig
from praisonaiagents.config.feature_configs import ChunkingStrategy
from praisonaiagents.knowledge.chunking import Chunking


@pytest.fixture
def source(tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text("The sky is blue.")
    return str(p)


def _built(source, **kw):
    agent = Agent(instructions="x", knowledge=KnowledgeConfig(sources=[source], **kw))
    agent._ensure_knowledge_processed()
    return agent._retrieval_config, agent.knowledge


@pytest.mark.parametrize("kwargs,probe,expected", [
    (dict(chunk_size=4000),                    lambda rc, k: k.chunker.chunk_size,        4000),
    (dict(chunk_overlap=7),                    lambda rc, k: k.chunker.chunk_overlap,     7),
    (dict(chunking_strategy="sentence"),       lambda rc, k: k.chunker.chunker_type,      "sentence"),
    (dict(chunking_strategy="fixed"),          lambda rc, k: k.chunker.chunker_type,      "token"),
    (dict(chunker={"type": "token"}),          lambda rc, k: k.chunker.chunker_type,      "token"),
    (dict(vector_store={"provider": "sqlite"}), lambda rc, k: rc.vector_store_provider,   "sqlite"),
    (dict(auto_retrieve=False),                lambda rc, k: rc.enabled,                  False),
    (dict(rerank_model="cohere/rerank-v3"),    lambda rc, k: rc.rerank_model,             "cohere/rerank-v3"),
    (dict(retrieval_threshold=0.77),           lambda rc, k: rc.min_score,                0.77),
    (dict(retrieval_k=20),                     lambda rc, k: rc.top_k,                    20),
    (dict(rerank=True),                        lambda rc, k: rc.rerank,                   True),
])
def test_field_reaches_internal_config(source, kwargs, probe, expected):
    rc, k = _built(source, **kwargs)
    assert probe(rc, k) == expected


def test_config_escape_hatch_does_not_wipe_other_fields(source):
    """config={...} must override, not replace, the resolved settings."""
    rc, _ = _built(source, retrieval_k=20, config={"note": "mine"})
    assert rc.top_k == 20


def test_config_escape_hatch_still_wins(source):
    rc, _ = _built(source, retrieval_k=20, config={"top_k": 3})
    assert rc.top_k == 3


def test_chunking_strategy_enum_resolves_to_a_real_chunker():
    """Every ChunkingStrategy member must map onto an implemented chunker."""
    from praisonaiagents.knowledge.chunking import normalize_chunker_type
    for strategy in ChunkingStrategy:
        assert normalize_chunker_type(strategy.value) in Chunking.CHUNKER_PARAMS


def test_unknown_chunking_strategy_raises():
    from praisonaiagents.knowledge.chunking import normalize_chunker_type
    with pytest.raises(ValueError, match="wordwise"):
        normalize_chunker_type("wordwise")


def test_declared_chunking_defaults_match_what_knowledge_builds(source):
    """The declared defaults must equal the effective ones (no silent drift)."""
    from praisonaiagents.knowledge.chunking import normalize_chunker_type
    cfg = KnowledgeConfig()
    _, k = _built(source)
    assert k.chunker.chunk_size == cfg.chunk_size
    assert k.chunker.chunk_overlap == cfg.chunk_overlap
    assert k.chunker.chunker_type == normalize_chunker_type(cfg.chunking_strategy.value)


def test_retrieval_config_round_trips_the_new_fields():
    """to_dict/from_dict must not drop the newly forwarded settings."""
    from praisonaiagents.rag.retrieval_config import RetrievalConfig
    cfg = RetrievalConfig(rerank_model="m", chunking_strategy="token",
                          chunk_size=999, chunk_overlap=11)
    back = RetrievalConfig.from_dict(cfg.to_dict())
    assert (back.rerank_model, back.chunking_strategy, back.chunk_size,
            back.chunk_overlap) == ("m", "token", 999, 11)


def test_rerank_model_emits_provider_for_knowledge():
    """rerank_model must reach Knowledge with a provider (mem0 needs one)."""
    from praisonaiagents.rag.retrieval_config import RetrievalConfig
    cfg = RetrievalConfig(rerank=True, rerank_model="cohere/rerank-v3")
    reranker = cfg.to_knowledge_config()["reranker"]
    assert reranker["provider"] == "cohere"
    assert reranker["config"] == {"model": "cohere/rerank-v3"}


def test_rerank_model_without_slash_uses_model_as_provider():
    from praisonaiagents.rag.retrieval_config import RetrievalConfig
    cfg = RetrievalConfig(rerank=True, rerank_model="simple")
    reranker = cfg.to_knowledge_config()["reranker"]
    assert reranker["provider"] == "simple"
