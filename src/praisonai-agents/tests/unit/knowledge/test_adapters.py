"""
Unit tests for Knowledge Adapters.

Tests Mem0Adapter lazy loading and normalization.
"""

import sys
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
