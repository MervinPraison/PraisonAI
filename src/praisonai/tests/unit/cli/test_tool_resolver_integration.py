"""
Smoke tests for CLI tool resolution via ToolResolver.

Tests for PR #1857 ensuring CLI tool loading uses unified ToolResolver
instead of direct TOOL_MAPPINGS access.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from praisonai.cli.main import PraisonCLI


class TestCLIToolResolverSmoke:
    """Smoke tests for CLI tool resolution integration."""

    def test_load_tools_imports_tool_resolver(self):
        """Test that _load_tools imports ToolResolver from correct module."""
        cli = PraisonCLI()
        
        # Mock the ToolResolver import
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_instance.resolve.return_value = None  # No tools found
            
            # Call _load_tools - should import and use ToolResolver
            result = cli._load_tools("nonexistent_tool")
            
            # Verify ToolResolver was imported and instantiated
            MockResolver.assert_called_once()
            assert result == []

    def test_load_tools_resolver_instantiation_pattern(self):
        """Test that ToolResolver is instantiated correctly."""
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_instance.resolve.return_value = Mock()  # Mock tool
            
            cli._load_tools("test_tool")
            
            # Should create instance with no arguments (default constructor)
            MockResolver.assert_called_once_with()

    def test_load_tools_calls_resolve_with_instantiate_true(self):
        """Test that resolve is called with instantiate=True."""
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_tool = Mock()
            mock_instance.resolve.return_value = mock_tool
            
            result = cli._load_tools("test_tool")
            
            # Verify resolve was called with instantiate=True
            mock_instance.resolve.assert_called_once_with("test_tool", instantiate=True)
            assert mock_tool in result

    def test_load_tools_multiple_comma_separated(self):
        """Test loading multiple comma-separated tools."""
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            
            # Different return values for different tools
            mock_tool1 = Mock()
            mock_tool2 = Mock()
            mock_instance.resolve.side_effect = [mock_tool1, mock_tool2]
            
            result = cli._load_tools("tool1,tool2")
            
            # Should call resolve twice
            assert mock_instance.resolve.call_count == 2
            mock_instance.resolve.assert_any_call("tool1", instantiate=True)
            mock_instance.resolve.assert_any_call("tool2", instantiate=True)
            assert mock_tool1 in result
            assert mock_tool2 in result

    def test_load_tools_whitespace_handling(self):
        """Test that whitespace around tool names is handled correctly."""
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_tool = Mock()
            mock_instance.resolve.return_value = mock_tool
            
            # Test with various whitespace combinations
            result = cli._load_tools(" tool1 , tool2  ,  tool3 ")
            
            # Should strip whitespace from tool names
            assert mock_instance.resolve.call_count == 3
            mock_instance.resolve.assert_any_call("tool1", instantiate=True)
            mock_instance.resolve.assert_any_call("tool2", instantiate=True)
            mock_instance.resolve.assert_any_call("tool3", instantiate=True)

    def test_load_tools_empty_string_filtering(self):
        """Test that empty strings are filtered out."""
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_tool = Mock()
            mock_instance.resolve.return_value = mock_tool
            
            # Include empty strings and whitespace-only strings
            result = cli._load_tools("tool1,,  , tool2,")
            
            # Should only resolve actual tool names
            assert mock_instance.resolve.call_count == 2
            mock_instance.resolve.assert_any_call("tool1", instantiate=True)
            mock_instance.resolve.assert_any_call("tool2", instantiate=True)

    def test_load_tools_none_return_handling(self):
        """Test handling when resolver returns None (tool not found)."""
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_instance.resolve.return_value = None  # Tool not found
            
            result = cli._load_tools("unknown_tool")
            
            # Should handle None return gracefully
            mock_instance.resolve.assert_called_once_with("unknown_tool", instantiate=True)
            assert result == []

    def test_load_tools_exception_handling(self):
        """Test that exceptions during tool resolution are handled gracefully."""
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_instance.resolve.side_effect = Exception("Tool resolution error")
            
            # Should not raise, should handle exception gracefully
            result = cli._load_tools("problematic_tool")
            
            # Should attempt resolution but return empty list on error
            mock_instance.resolve.assert_called_once_with("problematic_tool", instantiate=True)
            assert result == []

    def test_load_tools_file_path_bypass(self):
        """Test that file paths bypass the ToolResolver and use file loading."""
        cli = PraisonCLI()
        
        # Mock os.path.isfile to return True for file path test
        with patch('os.path.isfile', return_value=True):
            with patch('praisonai.cli.main.ToolResolver') as MockResolver:
                # Also need to mock the file loading parts
                with patch('praisonai.cli.main.load_user_module', return_value=None):
                    result = cli._load_tools("/path/to/tools.py")
                
                # ToolResolver should NOT be called for file paths
                MockResolver.assert_not_called()

    def test_load_tools_empty_input(self):
        """Test handling of empty or None input."""
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            # Test empty string
            result = cli._load_tools("")
            assert result == []
            MockResolver.assert_not_called()
            
            # Test None (if passed somehow)
            result = cli._load_tools(None)
            assert result == []
            MockResolver.assert_not_called()

    def test_load_tools_preserves_tool_instances(self):
        """Test that tool instances returned by resolver are preserved."""
        cli = PraisonCLI()
        
        # Create mock tools with specific attributes
        mock_tool1 = Mock()
        mock_tool1.name = "tool1"
        mock_tool2 = Mock() 
        mock_tool2.name = "tool2"
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_instance.resolve.side_effect = [mock_tool1, mock_tool2]
            
            result = cli._load_tools("tool1,tool2")
            
            # Should preserve exact tool instances
            assert len(result) == 2
            assert mock_tool1 in result
            assert mock_tool2 in result
            assert result[0].name == "tool1"
            assert result[1].name == "tool2"


class TestCLIToolResolverConsistency:
    """Test that CLI tool loading is consistent with other interfaces."""

    def test_resolver_import_path_consistency(self):
        """Test that CLI imports ToolResolver from the correct module path."""
        # This test ensures the import path is correct and consistent
        try:
            from praisonai.tool_resolver import ToolResolver
            from praisonai.cli.main import PraisonCLI
            
            # If both imports work, the path is consistent
            assert ToolResolver is not None
            assert PraisonCLI is not None
            
        except ImportError as e:
            pytest.fail(f"Import path inconsistency detected: {e}")

    def test_resolver_instantiation_consistency(self):
        """Test that CLI instantiates ToolResolver the same way as other components."""
        from praisonai.cli.main import PraisonCLI
        
        cli = PraisonCLI()
        
        # Mock to capture how ToolResolver is instantiated
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_instance.resolve.return_value = Mock()
            
            cli._load_tools("test_tool")
            
            # Should use default constructor (no arguments)
            MockResolver.assert_called_once_with()

    def test_resolve_method_signature_consistency(self):
        """Test that resolve method is called with expected signature."""
        from praisonai.cli.main import PraisonCLI
        
        cli = PraisonCLI()
        
        with patch('praisonai.cli.main.ToolResolver') as MockResolver:
            mock_instance = Mock()
            MockResolver.return_value = mock_instance
            mock_instance.resolve.return_value = Mock()
            
            cli._load_tools("test_tool")
            
            # Verify the method signature matches expectations
            mock_instance.resolve.assert_called_once_with("test_tool", instantiate=True)
            
            # Ensure no unexpected keyword arguments are passed
            call_args = mock_instance.resolve.call_args
            assert call_args[0] == ("test_tool",)  # positional args
            assert call_args[1] == {"instantiate": True}  # keyword args