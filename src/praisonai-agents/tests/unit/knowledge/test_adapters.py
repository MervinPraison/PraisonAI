"""
Unit tests for Knowledge Adapters.

Tests Mem0Adapter lazy loading and normalization.
"""

import sys
import importlib
from types import SimpleNamespace
import pytest
from unittest.mock import MagicMock

from praisonaiagents.knowledge.protocols import ScopeRequiredError


class TestMem0AdapterLazyLoading:
    """Tests for Mem0Adapter lazy import behavior."""
    
    def test_mem0_not_imported_at_module_level(self):
        """Test that mem0 is not imported when adapter module is imported."""
        # Remove mem0 from sys.modules if present
        mem0_modules = [k for k in sys.modules.keys() if k.startswith('mem0')]
        for mod in mem0_modules:
            sys.modules.pop(mod, None)
        
        # Import the adapter module
        from praisonaiagents.knowledge.adapters import mem0_adapter
        
        # mem0 should NOT be in sys.modules yet
        assert 'mem0' not in sys.modules, "mem0 should not be imported at module level"
    
    def test_adapter_class_importable(self):
        """Test that Mem0Adapter class can be imported."""
        from praisonaiagents.knowledge.adapters import Mem0Adapter
        assert Mem0Adapter is not None


class TestMem0AdapterNormalization:
    """Tests for Mem0Adapter result normalization."""
    
    def test_normalize_mem0_item_with_none_metadata(self):
        """Test normalization of mem0 result with metadata=None."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter
        
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._config = {}
        adapter._memory = None
        adapter._disable_telemetry = True
        
        raw = {
            "id": "test-id",
            "memory": "test content",
            "score": 0.95,
            "metadata": None,  # mem0 returns this!
            "user_id": "user123",
        }
        
        item = adapter._normalize_mem0_item(raw)
        
        assert item.id == "test-id"
        assert item.text == "test content"
        assert item.score == 0.95
        assert item.metadata == {"user_id": "user123"}  # user_id added
        assert item.metadata is not None
    
    def test_normalize_mem0_results_with_none_items(self):
        """Test normalization filters out None items."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter
        
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._config = {}
        adapter._memory = None
        adapter._disable_telemetry = True
        
        raw = {
            "results": [
                {"id": "1", "memory": "content 1", "metadata": None},
                None,
                {"id": "2", "memory": "content 2", "metadata": {"key": "val"}},
            ]
        }
        
        result = adapter._normalize_mem0_results(raw)
        
        assert len(result.results) == 2
        assert result.results[0].text == "content 1"
        assert result.results[0].metadata == {}
        assert result.results[1].metadata == {"key": "val"}


class TestMem0AdapterScopeValidation:
    """Tests for Mem0Adapter scope validation."""
    
    def test_search_requires_scope(self):
        """Test that search raises ScopeRequiredError without scope."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter
        
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._config = {}
        adapter._memory = MagicMock()
        adapter._disable_telemetry = True
        
        with pytest.raises(Exception, match="user_id.*agent_id|agent_id.*user_id"):
            adapter.search("query")
    
    def test_search_with_user_id_succeeds(self):
        """Test that search succeeds with user_id."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter
        
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._config = {}
        adapter._disable_telemetry = True
        
        # Mock the memory object
        mock_memory = MagicMock()
        mock_memory.search.return_value = {
            "results": [
                {"id": "1", "memory": "content", "metadata": None, "score": 0.9}
            ]
        }
        adapter._memory = mock_memory
        
        result = adapter.search("query", user_id="user123")
        
        assert len(result.results) == 1
        mock_memory.search.assert_called_once()
    
    def test_add_requires_scope(self):
        """Test that add raises ScopeRequiredError without scope."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter
        
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._config = {}
        adapter._memory = MagicMock()
        adapter._disable_telemetry = True
        
        with pytest.raises(Exception, match="user_id.*agent_id|agent_id.*user_id"):
            adapter.add("content")
    
    def test_get_all_requires_scope(self):
        """Test that get_all raises ScopeRequiredError without scope."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter
        
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._config = {}
        adapter._memory = MagicMock()
        adapter._disable_telemetry = True
        
        with pytest.raises(Exception, match="user_id.*agent_id|agent_id.*user_id"):
            adapter.get_all()
    
    def test_delete_all_requires_scope(self):
        """Test that delete_all raises ScopeRequiredError without scope."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter
        
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._config = {}
        adapter._memory = MagicMock()
        adapter._disable_telemetry = True
        
        with pytest.raises(Exception, match="user_id.*agent_id|agent_id.*user_id"):
            adapter.delete_all()


class TestProtocolCompliance:
    """Tests for KnowledgeStoreProtocol compliance."""
    
    def test_adapter_has_required_methods(self):
        """Test that Mem0Adapter has all protocol methods."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter
        
        required_methods = [
            'search', 'add', 'get', 'get_all', 
            'update', 'delete', 'delete_all'
        ]
        
        for method in required_methods:
            assert hasattr(Mem0Adapter, method), f"Missing method: {method}"


class TestAdapterVerboseKwarg:
    """Regression tests for issue #2972.

    Adapter constructors must accept the ``verbose`` keyword (and extra kwargs)
    passed by ``Knowledge.memory`` via the registry. Previously, ``Mem0Adapter``
    and ``MongoDBKnowledgeAdapter`` raised ``TypeError`` on ``verbose``, which was
    silently swallowed and degraded configured semantic search to SQLite keyword
    matching.
    """

    def test_mem0_adapter_accepts_verbose(self):
        """Mem0Adapter.__init__ must accept verbose without raising."""
        from praisonaiagents.knowledge.adapters.mem0_adapter import Mem0Adapter

        adapter = Mem0Adapter(config={}, verbose=5)
        assert isinstance(adapter, Mem0Adapter)

    def test_mongodb_adapter_signature_accepts_verbose(self):
        """MongoDBKnowledgeAdapter.__init__ must declare a verbose parameter."""
        import inspect
        from praisonaiagents.knowledge.adapters.mongodb_adapter import (
            MongoDBKnowledgeAdapter,
        )

        params = inspect.signature(MongoDBKnowledgeAdapter.__init__).parameters
        assert "verbose" in params or any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
        )

    def test_registry_constructs_mem0_with_verbose(self):
        """Registry should construct mem0 adapter with verbose, not fall back."""
        from praisonaiagents.knowledge.adapters import get_knowledge_adapter

        adapter = get_knowledge_adapter("mem0", config={}, verbose=1)
        assert type(adapter).__name__ == "Mem0Adapter"

    def test_knowledge_mem0_provider_not_silently_degraded(self):
        """Knowledge configured for mem0 must not silently fall back to SQLite.

        A ``verbose`` TypeError in the adapter constructor previously caused a
        silent degradation to ``SQLiteKnowledgeAdapter``. With the fix, the
        configured provider must be constructed (or, if mem0 is unavailable in
        the environment, at least not degraded because of a constructor-signature
        mismatch).
        """
        pytest.importorskip("mem0")
        from praisonaiagents.knowledge import Knowledge

        k = Knowledge(config={"vector_store": {"provider": "mem0", "config": {}}})
        assert type(k.memory).__name__ == "Mem0Adapter"

    def test_default_knowledge_does_not_warn_on_expected_fallback(self, caplog):
        """Default ``Knowledge()`` must not log a warning when falling back.

        When no provider is explicitly configured, ``mem0`` is only an implicit
        default. Falling back to SQLite (e.g. mem0 not installed) is the expected
        path and must not emit misleading ``logger.warning`` output about reduced
        retrieval quality (PR #2982 review).
        """
        import logging
        from praisonaiagents.knowledge import Knowledge

        with caplog.at_level(logging.WARNING, logger="praisonaiagents.knowledge.knowledge"):
            _ = Knowledge().memory

        degradation_warnings = [
            r.message for r in caplog.records
            if r.levelno >= logging.WARNING and "Retrieval quality may be reduced" in r.message
        ]
        assert degradation_warnings == [], (
            f"Default Knowledge() should not warn about degraded retrieval: "
            f"{degradation_warnings}"
        )

    def test_explicit_provider_warns_on_fallback(self, caplog):
        """Explicitly configured provider must warn loudly if it degrades.

        This is the whole point of issue #2972: a user who asks for a semantic
        backend should get a visible warning when it silently degrades. Uses
        ``chroma`` which is an optional dependency; when unavailable the adapter
        fails and Knowledge falls back, which must produce a visible warning.
        """
        pytest.importorskip("praisonaiagents.knowledge")
        try:
            import chromadb  # noqa: F401
            pytest.skip("chromadb installed; explicit chroma provider would not fall back")
        except ImportError:
            pass

        import logging
        from praisonaiagents.knowledge import Knowledge

        k = Knowledge(config={"vector_store": {"provider": "chroma", "config": {}}})
        with caplog.at_level(logging.WARNING, logger="praisonaiagents.knowledge.knowledge"):
            _ = k.memory

        warned = any(
            r.levelno >= logging.WARNING and "Retrieval quality may be reduced" in r.message
            for r in caplog.records
        )
        assert warned, "Explicitly configured provider should warn on fallback"


class TestChromaKnowledgeAdapterWhereFilters:
    """Tests for ChromaKnowledgeAdapter where-filter formatting."""

    def _make_adapter(self):
        from praisonaiagents.knowledge.adapters.factories import ChromaKnowledgeAdapter

        adapter = ChromaKnowledgeAdapter.__new__(ChromaKnowledgeAdapter)
        adapter.collection = MagicMock()
        adapter.collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }
        return adapter

    def test_search_wraps_multiple_where_filters_with_and(self, monkeypatch):
        embedding_module = importlib.import_module("praisonaiagents.embedding")

        adapter = self._make_adapter()
        monkeypatch.setattr(
            embedding_module,
            "embedding",
            lambda *args, **kwargs: SimpleNamespace(embeddings=[[0.1, 0.2]]),
            raising=False,
        )

        adapter.search("q", user_id="u1", agent_id="a1", run_id="r1")

        where = adapter.collection.query.call_args.kwargs["where"]
        assert where == {
            "$and": [{"user_id": "u1"}, {"agent_id": "a1"}, {"run_id": "r1"}]
        }

    def test_search_keeps_single_where_filter_unwrapped(self, monkeypatch):
        embedding_module = importlib.import_module("praisonaiagents.embedding")

        adapter = self._make_adapter()
        monkeypatch.setattr(
            embedding_module,
            "embedding",
            lambda *args, **kwargs: SimpleNamespace(embeddings=[[0.1, 0.2]]),
            raising=False,
        )

        adapter.search("q", user_id="u1")

        where = adapter.collection.query.call_args.kwargs["where"]
        assert where == {"user_id": "u1"}
