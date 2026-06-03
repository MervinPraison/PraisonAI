"""Integration tests for the ALLOWED_TOOLS filter module."""
import os
import pytest
from unittest.mock import patch, MagicMock
from praisonai.cli.features.agents import MultiAgentHandler


class TestAllowedToolsFilterRegistryIntegration:
    """Integration tests for ALLOWED_TOOLS filter with the tool registry."""
    
    def test_registry_allowed_filter_unset(self):
        """Test registry filter behavior when ALLOWED_TOOLS is unset."""
        from praisonaiagents.tools.registry import get_registry
        
        with patch.dict(os.environ, {}, clear=True):
            registry = get_registry()
            
            # Mock some tools in the registry
            with patch.object(registry, 'list_tools', return_value=['search_web', 'send_email']):
                filtered_tools = registry.list_tools_with_allowed_filter()
                
                # Should return all tools when unset
                assert set(filtered_tools) == {'search_web', 'send_email'}
    
    def test_registry_allowed_filter_with_whitelist(self):
        """Test registry filter with ALLOWED_TOOLS whitelist."""
        from praisonaiagents.tools.registry import get_registry
        
        with patch.dict(os.environ, {
            "ALLOWED_TOOLS": "search_web,send_email,unknown_tool",
            "CI": "false",
        }):
            registry = get_registry()
            
            # Mock some tools in the registry
            with patch.object(registry, 'list_tools', return_value=['search_web', 'send_email', 'extract_pdf']):
                filtered_tools = registry.list_tools_with_allowed_filter()
                
                # Should only include whitelisted tools that are available
                assert set(filtered_tools) == {'search_web', 'send_email'}
    
    def test_registry_allowed_filter_empty_result(self):
        """Test registry filter when no tools match whitelist."""
        from praisonaiagents.tools.registry import get_registry
        
        with patch.dict(os.environ, {
            "ALLOWED_TOOLS": "nonexistent_tool1,nonexistent_tool2",
            "CI": "false",
        }):
            registry = get_registry()
            
            # Mock some tools in the registry
            with patch.object(registry, 'list_tools', return_value=['search_web', 'send_email']):
                filtered_tools = registry.list_tools_with_allowed_filter()
                
                # Should return empty list when no matches
                assert filtered_tools == []
    
    def test_registry_allowed_filter_import_error_fallback(self):
        """Test registry filter fallback when import fails."""
        from praisonaiagents.tools.registry import get_registry
        
        registry = get_registry()
        
        with patch.object(registry, 'list_tools', return_value=['search_web', 'send_email']):
            # Mock import error for the filter
            with patch('praisonaiagents.tools.registry.filter_tools_with_allowed_tools', side_effect=ImportError("Filter not available")):
                filtered_tools = registry.list_tools_with_allowed_filter()
                
                # Should fallback to all tools
                assert set(filtered_tools) == {'search_web', 'send_email'}
    
    def test_registry_allowed_filter_value_error_propagation(self):
        """Test that ValueError from filter is properly propagated."""
        from praisonaiagents.tools.registry import get_registry
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": ""}):  # Empty string should cause ValueError
            registry = get_registry()
            
            with patch.object(registry, 'list_tools', return_value=['search_web', 'send_email']):
                with pytest.raises(ValueError, match="cannot be empty"):
                    registry.list_tools_with_allowed_filter()
    
    def test_registry_allowed_filter_general_error_fallback(self):
        """Test registry filter fallback on general errors."""
        from praisonaiagents.tools.registry import get_registry
        
        registry = get_registry()
        
        with patch.object(registry, 'list_tools', return_value=['search_web', 'send_email']):
            # Mock a generic error during filtering
            with patch('praisonaiagents.tools.registry.filter_tools_with_allowed_tools', side_effect=RuntimeError("Some error")):
                filtered_tools = registry.list_tools_with_allowed_filter()
                
                # Should fallback to all tools on general errors
                assert set(filtered_tools) == {'search_web', 'send_email'}


class TestAllowedToolsFilterGlobalRegistryPath:
    """Test ALLOWED_TOOLS filter through the global registry function."""
    
    def test_global_list_tools_with_allowed_filter(self):
        """Test the global list_tools_with_allowed_filter function."""
        from praisonaiagents.tools import list_tools_with_allowed_filter
        from praisonaiagents.tools.registry import get_registry
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search_web,send_email"}):
            registry = get_registry()
            
            with patch.object(registry, 'list_tools_with_allowed_filter', return_value=['search_web', 'send_email']) as mock_filter:
                result = list_tools_with_allowed_filter()
                
                # Should call the registry method
                mock_filter.assert_called_once_with(None)
                assert result == ['search_web', 'send_email']
    
    def test_global_backward_compatibility_alias(self):
        """Test the backward compatibility alias for hermes filter."""
        from praisonaiagents.tools import list_tools_with_hermes_filter, list_tools_with_allowed_filter
        from praisonaiagents.tools.registry import get_registry
        
        registry = get_registry()
        
        with patch.object(registry, 'list_tools_with_allowed_filter', return_value=['search_web']) as mock_filter:
            # Both should call the same underlying function
            result1 = list_tools_with_allowed_filter()
            result2 = list_tools_with_hermes_filter()
            
            assert result1 == result2 == ['search_web']
            assert mock_filter.call_count == 2


class TestAllowedToolsFilterCLIIntegration:
    """Integration tests for ALLOWED_TOOLS filter with CLI agent handler."""
    
    def test_cli_agents_load_tools_no_filter(self):
        """Test CLI agent tool loading without ALLOWED_TOOLS filter."""
        handler = MultiAgentHandler(verbose=False)
        
        with patch.dict(os.environ, {}, clear=True):
            # Mock the tools import to avoid actual import dependencies
            with patch('praisonai.cli.features.agents.internet_search'), \
                 patch('praisonai.cli.features.agents.read_file'):
                
                tools = handler._load_tools(["internet_search", "read_file"])
                
                # Should load all requested tools when no filter
                assert len(tools) == 2
    
    def test_cli_agents_load_tools_with_filter(self):
        """Test CLI agent tool loading with ALLOWED_TOOLS filter."""
        handler = MultiAgentHandler(verbose=False)
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "internet_search"}):
            # Mock the tools and filter
            mock_internet_search = MagicMock()
            mock_read_file = MagicMock()
            
            with patch('praisonai.cli.features.agents.internet_search', mock_internet_search), \
                 patch('praisonai.cli.features.agents.read_file', mock_read_file):
                
                tools = handler._load_tools(["internet_search", "read_file"])
                
                # Should only load tools allowed by filter
                assert len(tools) == 1
                assert mock_internet_search in tools
                assert mock_read_file not in tools
    
    def test_cli_agents_load_tools_filter_error_handling(self):
        """Test CLI tool loading with ALLOWED_TOOLS filter error handling."""
        handler = MultiAgentHandler(verbose=False)
        requested = ["internet_search", "read_file"]
        
        with patch('os.environ.get', return_value=None):
            with patch('praisonai.cli.features.agents.internet_search'), \
                 patch('praisonai.cli.features.agents.read_file'):
                baseline_tools = handler._load_tools(requested)
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": ""}):
            with pytest.raises(ValueError):
                handler._load_tools(requested)
    
    def test_cli_agents_load_tools_import_error_fallback(self):
        """Test CLI tool loading fallback when ALLOWED_TOOLS filter import fails."""
        handler = MultiAgentHandler(verbose=False)
        
        # Mock ImportError for the filter module
        with patch('praisonai.cli.features.agents.filter_tools_with_allowed_tools', side_effect=ImportError("Filter module not available")):
            with patch('praisonai.cli.features.agents.internet_search'), \
                 patch('praisonai.cli.features.agents.read_file'):
                
                tools = handler._load_tools(["internet_search", "read_file"])
                
                # Should load all tools on import error
                assert len(tools) == 2
    
    def test_cli_agents_load_tools_filter_value_error_propagation(self):
        """Test that ValueError from filter is properly propagated in CLI."""
        handler = MultiAgentHandler(verbose=False)
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": ""}):  # Empty string causes ValueError
            with pytest.raises(ValueError, match="cannot be empty"):
                handler._load_tools(["internet_search"])


class TestAllowedToolsFilterSpecSemantics:
    """Test ALLOWED_TOOLS filter specification semantics."""
    
    def test_spec_semantics_unset_all_tools_visible(self):
        """Test spec: unset ALLOWED_TOOLS means all tools visible with warning."""
        from praisonaiagents.allowed_tools_filter import AllowedToolsFilter
        
        with patch.dict(os.environ, {}, clear=True):
            filter_instance = AllowedToolsFilter()
            available_tools = {"search", "send_message", "extract_pdf"}
            
            import logging
            with patch.object(logging.getLogger(), 'warning') as mock_warn:
                filtered = filter_instance.filter_tools(available_tools)
            
            # Should return all tools
            assert filtered == available_tools
            
            # Should warn about unset whitelist
            mock_warn.assert_called_once()
            assert "Tool whitelist is unset" in mock_warn.call_args[0][0]
    
    def test_spec_semantics_empty_string_error(self):
        """Test spec: empty ALLOWED_TOOLS string is an error."""
        from praisonaiagents.allowed_tools_filter import AllowedToolsFilter
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": ""}):
            with pytest.raises(ValueError, match="ALLOWED_TOOLS cannot be empty"):
                AllowedToolsFilter()
    
    def test_spec_semantics_whitelist_only_specified_visible(self):
        """Test spec: with ALLOWED_TOOLS values, only whitelisted tools visible."""
        from praisonaiagents.allowed_tools_filter import AllowedToolsFilter
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"}):
            filter_instance = AllowedToolsFilter()
            available_tools = {"search", "send_message", "extract_pdf", "analyze_code"}
            
            filtered = filter_instance.filter_tools(available_tools)
            
            # Should only return whitelisted tools
            assert filtered == {"search", "send_message"}
    
    def test_spec_semantics_unknown_tools_dev_warn_strip(self):
        """Test spec: unknown tools in dev mode are warned and stripped."""
        from praisonaiagents.allowed_tools_filter import AllowedToolsFilter
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search,unknown_tool", "CI": "false"}):
            filter_instance = AllowedToolsFilter()
            available_tools = {"search", "send_message"}
            
            import logging
            with patch.object(logging.getLogger(), 'warning') as mock_warn:
                filtered = filter_instance.filter_tools(available_tools)
            
            # Should return only known tools
            assert filtered == {"search"}
            
            # Should warn about unknown tools
            mock_warn.assert_called()
            assert "unknown_tool" in str(mock_warn.call_args[0][2])
    
    def test_spec_semantics_unknown_tools_ci_strict_fail(self):
        """Test spec: unknown tools in CI mode cause strict failure."""
        from praisonaiagents.allowed_tools_filter import AllowedToolsFilter
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search,unknown_tool", "CI": "true"}):
            filter_instance = AllowedToolsFilter()
            available_tools = {"search", "send_message"}
            
            with pytest.raises(ValueError, match="Unknown tools in ALLOWED_TOOLS"):
                filter_instance.filter_tools(available_tools)
    
    def test_spec_semantics_order_independence(self):
        """Test spec: whitelist order doesn't matter."""
        from praisonaiagents.allowed_tools_filter import AllowedToolsFilter
        
        available_tools = {"search", "send_message", "extract_pdf"}
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"}):
            filter1 = AllowedToolsFilter()
            result1 = filter1.filter_tools(available_tools)
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "send_message,search"}):
            filter2 = AllowedToolsFilter()
            result2 = filter2.filter_tools(available_tools)
        
        # Results should be the same regardless of order
        assert result1 == result2 == {"search", "send_message"}
    
    def test_spec_semantics_duplicate_isolation(self):
        """Test spec: duplicate tool names in whitelist are handled properly."""
        from praisonaiagents.allowed_tools_filter import AllowedToolsFilter
        
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search,search,send_message,search"}):
            filter_instance = AllowedToolsFilter()
            available_tools = {"search", "send_message", "extract_pdf"}
            
            filtered = filter_instance.filter_tools(available_tools)
            
            # Duplicates should be de-duplicated
            assert filtered == {"search", "send_message"}
            
            # Whitelist should be a set (no duplicates)
            whitelist = filter_instance.get_whitelist()
            assert whitelist == {"search", "send_message"}
    
    def test_spec_backward_compatibility_hermes_precedence(self):
        """Test spec: ALLOWED_TOOLS takes precedence over HERMES_ONLY_TOOLS."""
        from praisonaiagents.allowed_tools_filter import AllowedToolsFilter
        
        with patch.dict(os.environ, {
            "ALLOWED_TOOLS": "search,send_message",
            "HERMES_ONLY_TOOLS": "extract_pdf"
        }):
            filter_instance = AllowedToolsFilter()
            available_tools = {"search", "send_message", "extract_pdf"}
            
            filtered = filter_instance.filter_tools(available_tools)
            
            # Should use ALLOWED_TOOLS, not HERMES_ONLY_TOOLS
            assert filtered == {"search", "send_message"}
            assert filter_instance.env_var_name == "ALLOWED_TOOLS"