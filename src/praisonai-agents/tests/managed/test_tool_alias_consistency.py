"""
Tests for tool alias consistency across managed agent backends.

Ensures that the shared TOOL_ALIAS_MAP is properly imported and used
consistently between managed_agents.py and managed_local.py to prevent
contract drift and silent behavioral differences.
"""

from unittest import TestCase

# Try to import pytest, but make it optional since it's not installed
try:
    import pytest
except ImportError:
    pytest = None


class TestToolAliasConsistency(TestCase):
    """Test suite for tool alias mapping consistency."""
    
    def test_tool_alias_single_source_of_truth(self):
        """Assert module-level identity - both modules use the same dict object."""
        # Import the shared mapping
        from praisonai.integrations._tool_aliases import TOOL_ALIAS_MAP as shared_map
        
        # Import the mapping as used in managed_agents.py
        from praisonai.integrations.managed_agents import TOOL_ALIAS_MAP as agents_map
        
        # Import the mapping as used in managed_local.py
        from praisonai.integrations.managed_local import TOOL_ALIAS_MAP as local_map
        
        # Assert all three are the same object (module-level identity)
        assert shared_map is agents_map, "managed_agents.py should import the shared TOOL_ALIAS_MAP"
        assert shared_map is local_map, "managed_local.py should import the shared TOOL_ALIAS_MAP"
        assert agents_map is local_map, "Both modules should use the same dict object"
    
    def test_known_aliases_stable(self):
        """Lock in the final mapping so future changes need deliberate test updates."""
        from praisonai.integrations._tool_aliases import TOOL_ALIAS_MAP
        
        # Expected stable mapping based on consolidation decisions
        expected_mapping = {
            "bash": "execute_command",
            "read": "read_file",
            "write": "write_file", 
            "edit": "apply_diff",
            "glob": "list_files",
            "grep": "search_file",
            "search": "search_web",
            "web_search": "search_web",
        }
        
        # Assert the mapping matches exactly
        assert TOOL_ALIAS_MAP == expected_mapping, (
            f"TOOL_ALIAS_MAP has changed from expected stable mapping.\n"
            f"Expected: {expected_mapping}\n"
            f"Actual: {TOOL_ALIAS_MAP}\n"
            f"If this change is intentional, update this test."
        )
    
    def test_resolved_conflicts(self):
        """Verify that previously conflicting mappings are resolved consistently."""
        from praisonai.integrations._tool_aliases import TOOL_ALIAS_MAP
        
        # Test conflict resolutions based on issue analysis:
        
        # grep: chose 'search_file' over 'execute_command' 
        # (matches PraisonAI grep_tool.py built-in)
        assert TOOL_ALIAS_MAP["grep"] == "search_file"
        
        # web_fetch: no longer aliased
        # (kept original name as no web_crawl tool found, now handled via passthrough)
        assert "web_fetch" not in TOOL_ALIAS_MAP
        
        # edit: chose 'apply_diff' over 'write_file'
        # (matches PraisonAI code/tools/apply_diff.py)  
        assert TOOL_ALIAS_MAP["edit"] == "apply_diff"
    
    def test_backward_compatibility(self):
        """Verify that functions using the alias map maintain their signatures."""
        from praisonai.integrations.managed_agents import map_managed_tools
        
        # Test function signature and behavior is preserved
        test_tools = ["bash", "grep", "web_fetch", "unknown_tool", "web_search"]
        result = map_managed_tools(test_tools)
        
        expected = ["execute_command", "search_file", "web_fetch", "unknown_tool", "search_web"]
        assert result == expected, "map_managed_tools should map known tools and pass through unknown ones"
    
    def test_no_duplicate_definitions(self):
        """Ensure that TOOL_MAPPING and local TOOL_ALIAS_MAP definitions are removed."""
        # Check managed_agents.py doesn't have TOOL_MAPPING anymore
        from praisonai import integrations
        managed_agents_module = integrations.managed_agents
        
        # TOOL_MAPPING should not exist as a module-level variable
        assert not hasattr(managed_agents_module, 'TOOL_MAPPING'), (
            "TOOL_MAPPING should be removed from managed_agents.py"
        )
        
        # Behavioral check: both modules should expose the same (imported) alias map
        from praisonai.integrations.managed_agents import TOOL_ALIAS_MAP as a_map
        from praisonai.integrations.managed_local import TOOL_ALIAS_MAP as l_map
        assert a_map is l_map, "Both modules should share the same TOOL_ALIAS_MAP object"


if __name__ == "__main__":
    import unittest
    unittest.main()