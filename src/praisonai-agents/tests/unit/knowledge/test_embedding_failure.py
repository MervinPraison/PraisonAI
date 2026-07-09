"""
Unit tests for embedding-failure handling in the Chroma knowledge adapter
and Knowledge._process_single_input propagation.

Regression tests for the "false success" indexing bug where a failed
embedding produced AddResult(success=False) that was counted as a stored
chunk, leaving Chroma empty while the CLI reported success.
"""

from unittest.mock import MagicMock, patch

import pytest

from praisonaiagents.knowledge.adapters.factories import ChromaKnowledgeAdapter
from praisonaiagents.knowledge.models import AddResult, SearchResult


def _make_adapter():
    """Build a ChromaKnowledgeAdapter without running __init__ (no chromadb)."""
    adapter = ChromaKnowledgeAdapter.__new__(ChromaKnowledgeAdapter)
    adapter.collection = MagicMock()
    adapter.client = MagicMock()
    return adapter


def test_add_returns_failure_when_embedding_raises():
    """When embedding() raises, add() must return AddResult(success=False) with detail."""
    adapter = _make_adapter()

    def boom(*args, **kwargs):
        raise RuntimeError("403 model_not_found")

    with patch("praisonaiagents.embedding.embedding", side_effect=boom):
        result = adapter.add("Paris is the capital of France.")

    assert isinstance(result, AddResult)
    assert result.success is False
    assert "Failed to generate embedding" in result.message
    assert "403 model_not_found" in result.message
    adapter.collection.add.assert_not_called()


def test_search_returns_empty_when_embedding_raises():
    """When query embedding fails, search() returns an empty SearchResult (logged)."""
    adapter = _make_adapter()

    def boom(*args, **kwargs):
        raise RuntimeError("embedding down")

    with patch("praisonaiagents.embedding.embedding", side_effect=boom):
        result = adapter.search("Paris")

    assert isinstance(result, SearchResult)
    assert result.results == []


def test_add_uses_configurable_embedding_model(monkeypatch):
    """add() should respect OPENAI_EMBEDDING_MODEL env var."""
    adapter = _make_adapter()
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "custom-embed-model")

    captured = {}

    def fake_embedding(text, model=None):
        captured["model"] = model
        return MagicMock(embeddings=[[0.1, 0.2, 0.3]])

    with patch("praisonaiagents.embedding.embedding", side_effect=fake_embedding):
        result = adapter.add("hello")

    assert captured["model"] == "custom-embed-model"
    assert result.success is True


def test_process_single_input_raises_on_failed_addresult():
    """_process_single_input must raise when store() returns a failed AddResult."""
    from praisonaiagents.knowledge.knowledge import Knowledge

    knowledge = Knowledge.__new__(Knowledge)
    knowledge.store = MagicMock(
        return_value=AddResult(success=False, message="Failed to generate embedding: 403")
    )
    knowledge._emit_knowledge_event = MagicMock()
    knowledge._log = MagicMock()
    knowledge.normalize_content = lambda x: x

    with pytest.raises(RuntimeError, match="Failed to generate embedding"):
        knowledge._process_single_input("Paris is the capital of France")
