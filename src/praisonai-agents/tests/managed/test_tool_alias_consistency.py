"""
Tests for tool alias consistency across managed agent backends.

Ensures that the shared TOOL_ALIAS_MAP is properly imported and used
consistently between managed_agents.py and managed_local.py to prevent
contract drift and silent behavioral differences.
"""

import pytest
from unittest import TestCase


class TestToolAliasConsistency(TestCase):
    """Test suite for tool alias mapping consistency."""
    
    def test_tool_alias_single_source_of_truth(self):
        """Assert module-level identity - both modules use the same dict object."""
        # Import the shared mapping
        from praisonai.praisonai.integrations._tool_aliases import TOOL_ALIAS_MAP as shared_map
        
        # Import the mapping as used in managed_agents.py
        from praisonai.praisonai.integrations.managed_agents import TOOL_ALIAS_MAP as agents_map
        
        # Import the mapping as used in managed_local.py
        from praisonai.praisonai.integrations.managed_local import TOOL_ALIAS_MAP as local_map
        
        # Assert all three are the same object (module-level identity)
        assert shared_map is agents_map, "managed_agents.py should import the shared TOOL_ALIAS_MAP"
        assert shared_map is local_map, "managed_local.py should import the shared TOOL_ALIAS_MAP"
        assert agents_map is local_map, "Both modules should use the same dict object"
    
    def test_known_aliases_stable(self):
        """Lock in the final mapping so future changes need deliberate test updates."""
        from praisonai.praisonai.integrations._tool_aliases import TOOL_ALIAS_MAP
        
        # Expected stable mapping based on consolidation decisions
        expected_mapping = {
            "bash": "execute_command",
            "read": "read_file",
            "write": "write_file", 
            "edit": "apply_diff",
            "glob": "list_files",
            "grep": "search_file",
            "web_fetch": "web_fetch",
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
        from praisonai.praisonai.integrations._tool_aliases import TOOL_ALIAS_MAP
        
        # Test conflict resolutions based on issue analysis:
        
        # grep: chose 'search_file' over 'execute_command' 
        # (matches PraisonAI grep_tool.py built-in)
        assert TOOL_ALIAS_MAP["grep"] == "search_file"
        
        # web_fetch: chose 'web_fetch' over 'web_crawl' 
        # (keeping original name as no web_crawl tool found)
        assert TOOL_ALIAS_MAP["web_fetch"] == "web_fetch"
        
        # edit: chose 'apply_diff' over 'write_file'
        # (matches PraisonAI code/tools/apply_diff.py)  
        assert TOOL_ALIAS_MAP["edit"] == "apply_diff"
    
    def test_backward_compatibility(self):
        """Verify that functions using the alias map maintain their signatures."""
        from praisonai.praisonai.integrations.managed_agents import map_managed_tools
        
        # Test function signature and behavior is preserved
        test_tools = ["bash", "grep", "web_fetch", "unknown_tool", "web_search"]
        result = map_managed_tools(test_tools)
        
        expected = ["execute_command", "search_file", "web_fetch", "unknown_tool", "search_web"]
        assert result == expected, f"map_managed_tools should map known tools and pass through unknown ones"
    
    def test_no_duplicate_definitions(self):
        """Ensure that TOOL_MAPPING and local TOOL_ALIAS_MAP definitions are removed."""
        import inspect
        
        # Check managed_agents.py doesn't have TOOL_MAPPING anymore
        from praisonai.praisonai import integrations
        managed_agents_module = integrations.managed_agents
        
        # TOOL_MAPPING should not exist as a module-level variable
        assert not hasattr(managed_agents_module, 'TOOL_MAPPING'), (
            "TOOL_MAPPING should be removed from managed_agents.py"
        )
        
        # Check that managed_local.py source doesn't contain local definition
        import praisonai.praisonai.integrations.managed_local as managed_local_module
        source = inspect.getsource(managed_local_module)
        
        # Should not have a local TOOL_ALIAS_MAP definition
        assert 'TOOL_ALIAS_MAP = {' not in source, (
            "Local TOOL_ALIAS_MAP definition should be removed from managed_local.py"
        )
        
        # Should import from _tool_aliases
        assert 'from ._tool_aliases import TOOL_ALIAS_MAP' in source, (
            "managed_local.py should import TOOL_ALIAS_MAP from _tool_aliases"
        )


if __name__ == "__main__":
    pytest.main([__file__])