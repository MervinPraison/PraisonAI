"""
Unit tests for MCP registry bridge adapter.

Tests the bridge between praisonaiagents.tools and praisonai.mcp_server registry.
"""

from unittest.mock import patch, MagicMock
from praisonai.mcp_server.adapters.tools_bridge import (
    is_bridge_available,
    _infer_tool_hints,
    _extract_category,
    _create_lazy_handler,
)


class TestBridgeAvailability:
    """Test bridge availability detection."""
    
    def test_is_bridge_available_when_installed(self):
        """Test detection when praisonaiagents is installed."""
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = MagicMock()  # Non-None means found
            assert is_bridge_available() is True
    
    def test_is_bridge_available_when_not_installed(self):
        """Test detection when praisonaiagents is not installed."""
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = None
            assert is_bridge_available() is False


class TestToolHintInference:
    """Test tool hint inference from names."""
    
    def test_read_only_patterns(self):
        """Test read-only hint inference."""
        read_only_names = [
            "memory.show",
            "data.list",
            "config.get",
            "file.read",
            "web.search",
            "db.find",
            "api.query",
            "status.info",
        ]
        
        for name in read_only_names:
            hints = _infer_tool_hints(name)
            assert hints["read_only_hint"] is True, f"{name} should be read-only"
            assert hints["destructive_hint"] is False, f"{name} should not be destructive"
    
    def test_destructive_default(self):
        """Test default destructive hint for unknown patterns."""
        hints = _infer_tool_hints("file.modify")
        assert hints["destructive_hint"] is True
        assert hints["read_only_hint"] is False
    
    def test_idempotent_patterns(self):
        """Test idempotent hint inference."""
        idempotent_names = [
            "config.set",
            "state.update",
            "settings.configure",
        ]
        
        for name in idempotent_names:
            hints = _infer_tool_hints(name)
            assert hints["idempotent_hint"] is True, f"{name} should be idempotent"
    
    def test_closed_world_patterns(self):
        """Test closed-world (openWorldHint=False) inference."""
        closed_world_names = [
            "memory.store",
            "session.create",
            "config.save",
            "local.cache",
        ]
        
        for name in closed_world_names:
            hints = _infer_tool_hints(name)
            assert hints["open_world_hint"] is False, f"{name} should be closed-world"
    
    def test_open_world_default(self):
        """Test default open-world hint."""
        hints = _infer_tool_hints("web.fetch")
        assert hints["open_world_hint"] is True


class TestCategoryExtraction:
    """Test category extraction from tool names."""
    
    def test_extract_category_standard(self):
        """Test standard category extraction."""
        assert _extract_category("praisonai.memory.show") == "memory"
        assert _extract_category("praisonai.web.search") == "web"
        assert _extract_category("praisonai.file.read") == "file"
    
    def test_extract_category_short_name(self):
        """Test category extraction from short names."""
        assert _extract_category("tool.action") == "tool"
    
    def test_extract_category_single_part(self):
        """Test category extraction from single-part names."""
        assert _extract_category("tool") is None


class TestLazyHandler:
    """Test lazy handler creation."""
    
    def test_create_lazy_handler_caches(self):
        """Test that lazy handler caches the loaded module."""
        with patch("importlib.import_module") as mock_import:
            mock_module = MagicMock()
            mock_module.test_func = MagicMock(return_value="result")
            mock_import.return_value = mock_module
            
            handler = _create_lazy_handler("test.module", None, "test.test_func")
            
            # First call should import
            handler()
            assert mock_import.call_count == 1
            
            # Second call should use cache
            handler()
            assert mock_import.call_count == 1  # Still 1, not 2
    
    def test_create_lazy_handler_class_based(self):
        """Test lazy handler for class-based tools."""
        with patch("importlib.import_module") as mock_import:
            mock_class = MagicMock()
            mock_instance = MagicMock()
            mock_instance.run = MagicMock(return_value="result")
            mock_class.return_value = mock_instance
            
            mock_module = MagicMock()
            mock_module.TestTool = mock_class
            mock_import.return_value = mock_module
            
            handler = _create_lazy_handler("test.module", "TestTool", "test.tool")
            handler()
            
            mock_class.assert_called_once()
            mock_instance.run.assert_called_once()
    
    def test_create_lazy_handler_error(self):
        """Test lazy handler error handling."""
        with patch("importlib.import_module") as mock_import:
            mock_import.side_effect = ImportError("Module not found")
            
            handler = _create_lazy_handler("nonexistent.module", None, "test.tool")
            
            try:
                handler()
                assert False, "Should have raised RuntimeError"
            except RuntimeError as e:
                assert "failed to load" in str(e).lower()


class TestBridgeRegistration:
    """Test bridge registration functionality."""
    
    @patch("praisonai.mcp_server.adapters.tools_bridge.is_bridge_available")
    def test_register_skips_when_unavailable(self, mock_available):
        """Test registration skips when praisonaiagents not available."""
        from praisonai.mcp_server.adapters.tools_bridge import register_praisonai_tools
        
        mock_available.return_value = False
        count = register_praisonai_tools()
        assert count == 0
    
    @patch("praisonai.mcp_server.adapters.tools_bridge.is_bridge_available")
    @patch("praisonai.mcp_server.adapters.tools_bridge.get_tool_mappings")
    @patch("praisonai.mcp_server.registry.get_tool_registry")
    def test_register_tools_from_mappings(self, mock_get_registry, mock_mappings, mock_available):
        """Test registering tools from TOOL_MAPPINGS."""
        from praisonai.mcp_server.adapters.tools_bridge import (
            register_praisonai_tools,
            _registered_tools,
            unregister_bridged_tools,
        )
        
        # Clean up any previous state
        _registered_tools.clear()
        
        mock_available.return_value = True
        mock_mappings.return_value = {
            "test.tool": ("test.module", "TestTool"),
        }
        
        mock_registry = MagicMock()
        mock_registry._tools = {}
        mock_registry.get.return_value = None
        mock_get_registry.return_value = mock_registry
        
        count = register_praisonai_tools()
        
        assert count == 1
        assert "praisonai.agents.test.tool" in mock_registry._tools
        
        # Clean up
        unregister_bridged_tools()
