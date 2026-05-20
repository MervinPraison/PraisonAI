"""
Tests for HERMES_ONLY_TOOLS filter module.

This module tests the canonical implementation of HERMES_ONLY_TOOLS filtering
to ensure it correctly prevents tool name collisions in multi-environment systems.
"""

import os
import pytest
from unittest.mock import patch
import logging

from praisonaiagents.hermes_filter import (
    HermesToolFilter,
    filter_tools_with_hermes,
    hermes_filter,
    apply_hermes_filter,
)


class TestHermesToolFilter:
    """Test the main HermesToolFilter class."""
    
    def test_init_default(self):
        """Test default initialization."""
        filter_instance = HermesToolFilter()
        assert filter_instance.env_var_name == "HERMES_ONLY_TOOLS"
        assert filter_instance.env_value is None
        assert not filter_instance.is_enabled()
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,send_message"})
    def test_init_with_env_var(self):
        """Test initialization with environment variable set."""
        filter_instance = HermesToolFilter()
        assert filter_instance.env_value == "search,send_message"
        assert filter_instance.is_enabled()
        assert filter_instance.get_whitelist() == {"search", "send_message"}
    
    @patch.dict(os.environ, {"CUSTOM_FILTER": "tool1,tool2"})
    def test_init_custom_env_var(self):
        """Test initialization with custom environment variable."""
        filter_instance = HermesToolFilter("CUSTOM_FILTER")
        assert filter_instance.env_var_name == "CUSTOM_FILTER"
        assert filter_instance.env_value == "tool1,tool2"
        assert filter_instance.get_whitelist() == {"tool1", "tool2"}
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": ""})
    def test_empty_string_raises_error(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            HermesToolFilter()
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "  ,  ,"})
    def test_empty_tools_raises_error(self):
        """Test that string with only commas/spaces raises ValueError."""
        with pytest.raises(ValueError, match="contains no valid tool names"):
            HermesToolFilter()
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": " tool1 , tool2 ,tool3"})
    def test_whitespace_handling(self):
        """Test proper whitespace handling in tool names."""
        filter_instance = HermesToolFilter()
        assert filter_instance.get_whitelist() == {"tool1", "tool2", "tool3"}
    
    def test_filter_tools_unset_env_var(self):
        """Test filtering with unset environment variable."""
        filter_instance = HermesToolFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        with patch('praisonaiagents.hermes_filter.logger.warning') as mock_warning:
            result = filter_instance.filter_tools(available_tools)
            
        assert result == available_tools
        mock_warning.assert_called_once()
        assert "unset" in mock_warning.call_args[0][0].lower()
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,send_message"})
    def test_filter_tools_with_whitelist(self):
        """Test filtering with whitelist set."""
        filter_instance = HermesToolFilter()
        available_tools = {"search", "send_message", "extract_pdf", "download"}
        
        result = filter_instance.filter_tools(available_tools)
        
        assert result == {"search", "send_message"}
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,unknown_tool,send_message", "CI": "false"})
    def test_filter_tools_with_unknown_tools_dev_mode(self):
        """Test filtering with unknown tools in development mode."""
        filter_instance = HermesToolFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        with patch('praisonaiagents.hermes_filter.logger.warning') as mock_warning:
            result = filter_instance.filter_tools(available_tools)
        
        assert result == {"search", "send_message"}
        mock_warning.assert_called_once()
        assert "unknown_tool" in str(mock_warning.call_args)
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,unknown_tool", "CI": "true"})
    def test_filter_tools_with_unknown_tools_ci_mode(self):
        """Test filtering with unknown tools in CI mode raises error."""
        filter_instance = HermesToolFilter()
        available_tools = {"search", "extract_pdf"}
        
        with pytest.raises(ValueError, match="Unknown tools.*unknown_tool"):
            filter_instance.filter_tools(available_tools)
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,send_message"})
    def test_filter_tools_with_dict_input(self):
        """Test filtering with dict input (tool names as keys)."""
        filter_instance = HermesToolFilter()
        available_tools = {
            "search": {"description": "Search function"},
            "send_message": {"description": "Send message function"},
            "extract_pdf": {"description": "PDF extraction"}
        }
        
        result = filter_instance.filter_tools(available_tools)
        
        assert result == {"search", "send_message"}
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,send_message"})
    def test_filter_tools_with_list_input(self):
        """Test filtering with list input."""
        filter_instance = HermesToolFilter()
        available_tools = ["search", "send_message", "extract_pdf"]
        
        result = filter_instance.filter_tools(available_tools)
        
        assert result == {"search", "send_message"}
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,send_message,unknown_in_whitelist"})
    def test_diagnostics_data(self):
        """Test diagnostics data collection."""
        filter_instance = HermesToolFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        filter_instance.filter_tools(available_tools)
        diagnostics = filter_instance.get_diagnostics()
        
        assert diagnostics["env_var_name"] == "HERMES_ONLY_TOOLS"
        assert diagnostics["env_value"] == "search,send_message,unknown_in_whitelist"
        assert set(diagnostics["whitelist"]) == {"search", "send_message", "unknown_in_whitelist"}
        assert set(diagnostics["registered_before_filter"]) == available_tools
        assert set(diagnostics["registered_after_filter"]) == {"search", "send_message"}
        assert set(diagnostics["dropped_tools"]) == {"extract_pdf"}
        assert diagnostics["unknown_tools"] == ["unknown_in_whitelist"]
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,send_message"})
    def test_log_diagnostics(self, caplog):
        """Test diagnostics logging."""
        filter_instance = HermesToolFilter()
        available_tools = {"search", "send_message", "extract_pdf"}
        
        filter_instance.filter_tools(available_tools)
        
        with caplog.at_level(logging.INFO):
            filter_instance.log_diagnostics()
        
        log_text = caplog.text
        assert "HERMES_ONLY_TOOLS DIAGNOSTICS" in log_text
        assert "HERMES_ONLY_TOOLS=search,send_message" in log_text
        assert "RegisteredBeforeFilter=" in log_text
        assert "RegisteredAfterFilter=" in log_text
        assert "DroppedTools=" in log_text
    
    def test_log_diagnostics_without_filtering(self, caplog):
        """Test diagnostics logging before filtering shows warning."""
        filter_instance = HermesToolFilter()
        
        with caplog.at_level(logging.WARNING):
            filter_instance.log_diagnostics()
        
        assert "No diagnostics available" in caplog.text
    
    @patch.dict(os.environ, {"CI": "1"})
    def test_ci_detection(self):
        """Test CI environment detection."""
        filter_instance = HermesToolFilter()
        assert filter_instance.is_ci
    
    @patch.dict(os.environ, {"CI": "false"})
    def test_ci_detection_false(self):
        """Test CI environment detection with false value."""
        filter_instance = HermesToolFilter()
        assert not filter_instance.is_ci


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "search,send_message"})
    def test_filter_tools_with_hermes(self):
        """Test the main convenience function."""
        available_tools = {"search", "send_message", "extract_pdf"}
        
        with patch('logging.info'):  # Suppress diagnostics logging
            result = filter_tools_with_hermes(available_tools, log_diagnostics=False)
        
        assert result == {"search", "send_message"}
    
    @patch.dict(os.environ, {"CUSTOM_VAR": "tool1,tool2"})
    def test_filter_tools_with_custom_env_var(self):
        """Test convenience function with custom environment variable."""
        available_tools = {"tool1", "tool2", "tool3"}
        
        with patch('logging.info'):  # Suppress diagnostics logging
            result = filter_tools_with_hermes(
                available_tools, 
                env_var_name="CUSTOM_VAR",
                log_diagnostics=False
            )
        
        assert result == {"tool1", "tool2"}
    
    def test_filter_tools_with_hermes_diagnostics_enabled(self, caplog):
        """Test convenience function with diagnostics enabled."""
        available_tools = {"search", "extract_pdf"}
        
        with caplog.at_level(logging.INFO):
            result = filter_tools_with_hermes(available_tools, log_diagnostics=True)
        
        # Should see warning about unset variable and no diagnostics section
        assert result == available_tools
        assert "unset" in caplog.text.lower()
    
    def test_compatibility_exports(self):
        """Test that compatibility exports work."""
        available_tools = {"search", "extract_pdf"}
        
        # Test hermes_filter alias
        result1 = hermes_filter(available_tools, log_diagnostics=False)
        assert result1 == available_tools
        
        # Test apply_hermes_filter alias
        result2 = apply_hermes_filter(available_tools, log_diagnostics=False)
        assert result2 == available_tools


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_available_tools(self):
        """Test filtering with no available tools."""
        filter_instance = HermesToolFilter()
        result = filter_instance.filter_tools(set())
        assert result == set()
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "tool1", "CI": "false"})
    def test_no_matching_tools(self):
        """Test filtering when no tools match the whitelist."""
        filter_instance = HermesToolFilter()
        available_tools = {"tool2", "tool3"}
        
        with patch('praisonaiagents.hermes_filter.logger.warning'):  # Suppress warning about unknown tools
            result = filter_instance.filter_tools(available_tools)
        
        assert result == set()
    
    @patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "tool1,tool2"})
    def test_all_tools_match(self):
        """Test filtering when all available tools are whitelisted."""
        filter_instance = HermesToolFilter()
        available_tools = {"tool1", "tool2"}
        
        result = filter_instance.filter_tools(available_tools)
        
        assert result == available_tools
    
    def test_whitelist_copy_safety(self):
        """Test that get_whitelist returns a safe copy."""
        with patch.dict(os.environ, {"HERMES_ONLY_TOOLS": "tool1,tool2"}):
            filter_instance = HermesToolFilter()
            whitelist = filter_instance.get_whitelist()
            
            # Modify the returned set
            whitelist.add("tool3")
            
            # Original whitelist should be unchanged
            assert filter_instance.get_whitelist() == {"tool1", "tool2"}


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""
    
    @patch.dict(os.environ, {
        "HERMES_ONLY_TOOLS": "internet_search,read_file,write_file"
    })
    def test_typical_agent_scenario(self):
        """Test a typical multi-agent scenario with overlapping tool names."""
        # Simulate environment with multiple modules registering tools
        env_tools = {"youtube_transcript_extract", "internet_search", "web_search"}
        twilio_tools = {"send_whatsapp_message", "send_sms", "internet_search"}  # collision!
        agent_tools = {"read_file", "write_file", "execute_command"}
        
        all_tools = env_tools | twilio_tools | agent_tools
        
        filter_instance = HermesToolFilter()
        filtered_tools = filter_instance.filter_tools(all_tools)
        
        # Should only get whitelisted tools, resolving collision by exclusion
        assert filtered_tools == {"internet_search", "read_file", "write_file"}
        
        diagnostics = filter_instance.get_diagnostics()
        expected_dropped = {
            "youtube_transcript_extract", "send_whatsapp_message", 
            "send_sms", "execute_command", "web_search"
        }
        assert set(diagnostics["dropped_tools"]) == expected_dropped
    
    def test_hermes_superpowers_integration_pattern(self):
        """Test the specific pattern mentioned in the issue for Hermes Superpowers."""
        # Simulate the pattern from the issue
        available_tools = {
            "youtube_transcript_extract",  # from env.youtube.*
            "send_whatsapp_message",       # from env.twilio.*
            "search",                      # collision from multiple modules
            "send_message",                # collision from multiple modules
        }
        
        with patch.dict(os.environ, {
            "HERMES_ONLY_TOOLS": "send_whatsapp_message,youtube_transcript_extract"
        }):
            result = filter_tools_with_hermes(available_tools, log_diagnostics=False)
        
        # Should resolve collisions by only allowing whitelisted tools
        assert result == {"send_whatsapp_message", "youtube_transcript_extract"}


if __name__ == "__main__":
    pytest.main([__file__])
