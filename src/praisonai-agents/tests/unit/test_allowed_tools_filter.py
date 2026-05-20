"""Unit tests for the ALLOWED_TOOLS filter module."""
import os
import logging
from unittest.mock import patch, MagicMock
import pytest

from praisonaiagents.allowed_tools_filter import AllowedToolsFilter, filter_tools_with_allowed_tools


class TestAllowedToolsFilter:
    """Test cases for AllowedToolsFilter class."""
    
    def test_filter_initialization_unset(self):
        """Test filter initialization with no environment variable set."""
        with patch.dict(os.environ, {}, clear=True):
            filter_instance = AllowedToolsFilter()
            assert filter_instance.env_value is None
            assert not filter_instance.is_enabled()
            assert filter_instance.get_whitelist() is None
    
    def test_filter_initialization_primary_var(self):
        """Test filter initialization with ALLOWED_TOOLS set."""
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"}):
            filter_instance = AllowedToolsFilter()
            assert filter_instance.env_value == "search,send_message"
            assert filter_instance.env_var_name == "ALLOWED_TOOLS"
            assert filter_instance.is_enabled()
            assert filter_instance.get_whitelist() == {"search", "send_message"}
    
    
    def test_filter_initialization_empty_string_error(self):
        """Test that empty string raises ValueError."""
        with patch.dict(os.environ, {"ALLOWED_TOOLS": ""}):
            with pytest.raises(ValueError, match="ALLOWED_TOOLS cannot be empty"):
                AllowedToolsFilter()
    
    def test_filter_initialization_whitespace_only_error(self):
        """Test that whitespace-only string raises ValueError."""
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "   "}):
            with pytest.raises(ValueError, match="ALLOWED_TOOLS cannot be empty"):
                AllowedToolsFilter()
    
    def test_filter_initialization_empty_after_split_error(self):
        """Test that comma-only string raises ValueError."""
        with patch.dict(os.environ, {"ALLOWED_TOOLS": ",,,"}):
            with pytest.raises(ValueError, match="contains no valid tool names"):
                AllowedToolsFilter()
    
    def test_parse_whitelist_with_spaces(self):
        """Test parsing comma-separated values with spaces."""
        with patch.dict(os.environ, {"ALLOWED_TOOLS": " search , send_message , extract_pdf "}):
            filter_instance = AllowedToolsFilter()
            assert filter_instance.get_whitelist() == {"search", "send_message", "extract_pdf"}
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,unknown_tool,send_message", "CI": "false"})
    def test_filter_tools_with_unknown_tools_dev_mode(self):
        """Test filtering tools with unknown tools in development mode."""
        filter_instance = AllowedToolsFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        with patch.object(logging.getLogger('praisonaiagents.allowed_tools_filter'), 'warning') as mock_warn:
            filtered = filter_instance.filter_tools(available_tools)
            
        # Should return intersection of available and whitelisted tools
        assert filtered == {"search", "send_message"}
        
        # Should warn about unknown tools
        mock_warn.assert_called()
        call_args = mock_warn.call_args[0]
        assert "Unknown tools" in call_args[0]
        assert ["unknown_tool"] == call_args[2]
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,unknown_tool,send_message", "CI": "true"})
    def test_filter_tools_with_unknown_tools_ci_mode(self):
        """Test filtering tools with unknown tools in CI mode."""
        filter_instance = AllowedToolsFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        with pytest.raises(ValueError, match="Unknown tools in ALLOWED_TOOLS"):
            filter_instance.filter_tools(available_tools)
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"})
    def test_filter_tools_all_available(self):
        """Test filtering when all whitelisted tools are available."""
        filter_instance = AllowedToolsFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        filtered = filter_instance.filter_tools(available_tools)
        assert filtered == {"search", "send_message"}
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message", "CI": "false"})
    def test_filter_tools_partial_match(self):
        """Test filtering when only some whitelisted tools are available."""
        filter_instance = AllowedToolsFilter()
        available_tools = {"search", "extract_pdf"}
        
        filtered = filter_instance.filter_tools(available_tools)
        assert filtered == {"search"}
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"})
    def test_filter_tools_dict_input(self):
        """Test filtering with dictionary input."""
        filter_instance = AllowedToolsFilter()
        available_tools = {"search": lambda: None, "send_message": lambda: None, "extract_pdf": lambda: None}
        
        filtered = filter_instance.filter_tools(available_tools)
        assert filtered == {"search", "send_message"}
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"})
    def test_filter_tools_list_input(self):
        """Test filtering with list input."""
        filter_instance = AllowedToolsFilter()
        available_tools = ["search", "send_message", "extract_pdf"]
        
        filtered = filter_instance.filter_tools(available_tools)
        assert filtered == {"search", "send_message"}
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message,unknown_in_whitelist", "CI": "false"})
    def test_diagnostics_data(self):
        """Test diagnostics data collection."""
        filter_instance = AllowedToolsFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        filtered = filter_instance.filter_tools(available_tools)
        diagnostics = filter_instance.get_diagnostics()
        
        assert diagnostics["env_var_name"] == "ALLOWED_TOOLS"
        assert diagnostics["env_value"] == "search,send_message,unknown_in_whitelist"
        assert diagnostics["whitelist"] == ["search", "send_message", "unknown_in_whitelist"]
        assert set(diagnostics["registered_before_filter"]) == {"search", "send_message", "extract_pdf"}
        assert set(diagnostics["registered_after_filter"]) == {"search", "send_message"}
        assert set(diagnostics["dropped_tools"]) == {"extract_pdf"}
        assert set(diagnostics["unknown_tools"]) == {"unknown_in_whitelist"}
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"})
    def test_log_diagnostics(self, caplog):
        """Test diagnostics logging."""
        filter_instance = AllowedToolsFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        with caplog.at_level(logging.INFO):
            filter_instance.filter_tools(available_tools)
            filter_instance.log_diagnostics()
        
        log_text = caplog.text
        assert "ALLOWED_TOOLS FILTER DIAGNOSTICS" in log_text
        assert "ALLOWED_TOOLS=search,send_message" in log_text
        assert "RegisteredBeforeFilter" in log_text
        assert "RegisteredAfterFilter" in log_text
        assert "DroppedTools" in log_text
        assert "UnknownTools" in log_text
    
    def test_log_diagnostics_before_filtering(self, caplog):
        """Test logging diagnostics before calling filter_tools."""
        filter_instance = AllowedToolsFilter()
        
        with caplog.at_level(logging.WARNING):
            filter_instance.log_diagnostics()
        
        assert "No diagnostics available" in caplog.text
    
    def test_filter_tools_unset_env_var(self, caplog):
        """Test filtering with unset environment variable."""
        with patch.dict(os.environ, {}, clear=True):
            filter_instance = AllowedToolsFilter()
            available_tools = {"search", "send_message", "extract_pdf"}
            
            with caplog.at_level(logging.WARNING):
                filtered = filter_instance.filter_tools(available_tools)
            
            # Should return all tools
            assert filtered == available_tools
            assert "Tool whitelist is unset" in caplog.text
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "tool1", "CI": "false"})
    def test_no_matching_tools(self):
        """Test filtering when no whitelisted tools match available tools."""
        filter_instance = AllowedToolsFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        filtered = filter_instance.filter_tools(available_tools)
        assert filtered == set()  # Empty set when no matches
    
    def test_custom_env_var_name(self):
        """Test using custom environment variable name."""
        with patch.dict(os.environ, {"CUSTOM_TOOLS": "search,send_message"}):
            filter_instance = AllowedToolsFilter("CUSTOM_TOOLS")
            assert filter_instance.env_var_name == "CUSTOM_TOOLS"
            assert filter_instance.get_whitelist() == {"search", "send_message"}
    
    def test_empty_tools_edge_case(self):
        """Test filtering with empty available tools."""
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message", "CI": "false"}):
            filter_instance = AllowedToolsFilter()
            
            filtered = filter_instance.filter_tools(set())
            assert filtered == set()
            
            # Also test with empty list and dict
            assert filter_instance.filter_tools([]) == set()
            assert filter_instance.filter_tools({}) == set()
    
    def test_whitelist_immutability(self):
        """Test that get_whitelist returns a copy, not the original."""
        with patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"}):
            filter_instance = AllowedToolsFilter()
            
            whitelist1 = filter_instance.get_whitelist()
            whitelist2 = filter_instance.get_whitelist()
            
            # Should be equal but not the same object
            assert whitelist1 == whitelist2
            assert whitelist1 is not whitelist2
            
            # Modifying one shouldn't affect the other
            whitelist1.add("new_tool")
            assert whitelist1 != whitelist2


class TestConvenienceFunction:
    """Test cases for the convenience function."""
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search,send_message"})
    def test_filter_tools_with_allowed_tools(self):
        """Test the convenience function."""
        available_tools = {"search", "send_message", "extract_pdf"}
        
        filtered = filter_tools_with_allowed_tools(available_tools, log_diagnostics=False)
        assert filtered == {"search", "send_message"}
    
    @patch.dict(os.environ, {"CUSTOM_TOOLS": "search"})
    def test_filter_tools_with_custom_env_var(self):
        """Test the convenience function with custom env var."""
        available_tools = {"search", "send_message"}
        
        filtered = filter_tools_with_allowed_tools(available_tools, env_var_name="CUSTOM_TOOLS", log_diagnostics=False)
        assert filtered == {"search"}
    
    @patch.dict(os.environ, {"ALLOWED_TOOLS": "search"})
    def test_filter_tools_with_diagnostics(self, caplog):
        """Test the convenience function with diagnostics enabled."""
        available_tools = {"search", "send_message"}
        
        with caplog.at_level(logging.INFO):
            filtered = filter_tools_with_allowed_tools(available_tools, log_diagnostics=True)
        
        assert filtered == {"search"}
        assert "ALLOWED_TOOLS FILTER DIAGNOSTICS" in caplog.text


