"""Tests for YAML tool resolution - TDD approach.

These tests verify that tool names in YAML files can be resolved to callables
from multiple sources:
1. Local tools.py (backward compat, custom tools)
2. praisonaiagents.tools.TOOL_MAPPINGS (built-in)
3. praisonai-tools package (external, optional)
"""

import time


class TestToolResolver:
    """Test suite for ToolResolver class."""
    
    def test_import_tool_resolver(self):
        """ToolResolver should be importable from praisonai."""
        from praisonai.tool_resolver import ToolResolver
        assert ToolResolver is not None
    
    def test_resolver_instantiation(self):
        """ToolResolver should instantiate without errors."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        assert resolver is not None
    
    def test_resolve_builtin_tool_tavily_search(self):
        """Should resolve 'tavily_search' from praisonaiagents.tools."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tool = resolver.resolve("tavily_search")
        assert tool is not None
        assert callable(tool)
    
    def test_resolve_builtin_tool_internet_search(self):
        """Should resolve 'internet_search' from praisonaiagents.tools."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tool = resolver.resolve("internet_search")
        assert tool is not None
        assert callable(tool)
    
    def test_resolve_builtin_tool_execute_command(self):
        """Should resolve 'execute_command' from praisonaiagents.tools."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tool = resolver.resolve("execute_command")
        assert tool is not None
        assert callable(tool)
    
    def test_resolve_nonexistent_tool_returns_none(self):
        """Should return None for unknown tool names."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tool = resolver.resolve("nonexistent_tool_xyz_123")
        assert tool is None
    
    def test_resolve_many_returns_list(self):
        """resolve_many should return list of callables."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tools = resolver.resolve_many(["tavily_search", "internet_search"])
        assert isinstance(tools, list)
        assert len(tools) == 2
        assert all(callable(t) for t in tools)
    
    def test_resolve_many_skips_missing_tools(self):
        """resolve_many should skip missing tools with warning."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tools = resolver.resolve_many(["tavily_search", "nonexistent_xyz"])
        assert len(tools) == 1  # Only tavily_search resolved
    
    def test_resolve_many_empty_list(self):
        """resolve_many with empty list returns empty list."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tools = resolver.resolve_many([])
        assert tools == []
    
    def test_list_available_returns_dict(self):
        """list_available should return dict of tool names to descriptions."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        available = resolver.list_available()
        assert isinstance(available, dict)
        assert len(available) > 0
        assert "tavily_search" in available
    
    def test_list_available_includes_builtin_tools(self):
        """list_available should include all TOOL_MAPPINGS entries."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        available = resolver.list_available()
        # Check some known built-in tools
        assert "tavily_search" in available
        assert "internet_search" in available
        assert "execute_command" in available
    
    def test_has_tool_returns_true_for_existing(self):
        """has_tool should return True for existing tools."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        assert resolver.has_tool("tavily_search") is True
    
    def test_has_tool_returns_false_for_missing(self):
        """has_tool should return False for missing tools."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        assert resolver.has_tool("nonexistent_xyz") is False


class TestToolResolverLocalTools:
    """Test local tools.py resolution."""
    
    def test_resolve_from_local_tools_py(self, tmp_path, monkeypatch):
        """Should resolve tools from local tools.py file."""
        # Create a temporary tools.py
        tools_py = tmp_path / "tools.py"
        tools_py.write_text('''
def my_custom_tool(query: str) -> str:
    """A custom tool for testing."""
    return f"Result: {query}"
''')
        
        # Change to temp directory
        monkeypatch.chdir(tmp_path)
        
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tool = resolver.resolve("my_custom_tool")
        
        assert tool is not None
        assert callable(tool)
        assert tool("test") == "Result: test"
    
    def test_local_tools_take_precedence(self, tmp_path, monkeypatch):
        """Local tools.py should override built-in tools with same name."""
        # Create a tools.py that overrides tavily_search
        tools_py = tmp_path / "tools.py"
        tools_py.write_text('''
def tavily_search(query: str) -> str:
    """Override tavily_search for testing."""
    return "LOCAL_OVERRIDE"
''')
        
        monkeypatch.chdir(tmp_path)
        
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        tool = resolver.resolve("tavily_search")
        
        assert tool is not None
        assert tool("test") == "LOCAL_OVERRIDE"


class TestToolResolverPraisonAITools:
    """Test praisonai-tools package resolution."""
    
    def test_resolve_from_praisonai_tools_if_installed(self):
        """Should resolve tools from praisonai-tools if installed."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        
        # Try to resolve EmailTool (from praisonai-tools)
        # This may or may not be installed
        # Just verify it doesn't crash - tool may be None if not installed
        _ = resolver.resolve("EmailTool")


class TestToolResolverValidation:
    """Test YAML validation functionality."""
    
    def test_validate_yaml_tools_all_valid(self):
        """validate_yaml_tools should return empty list for valid tools."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        
        yaml_config = {
            "roles": {
                "researcher": {
                    "tools": ["tavily_search", "internet_search"]
                }
            }
        }
        
        missing = resolver.validate_yaml_tools(yaml_config)
        assert missing == []
    
    def test_validate_yaml_tools_returns_missing(self):
        """validate_yaml_tools should return list of missing tool names."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        
        yaml_config = {
            "roles": {
                "researcher": {
                    "tools": ["tavily_search", "nonexistent_tool"]
                }
            }
        }
        
        missing = resolver.validate_yaml_tools(yaml_config)
        assert "nonexistent_tool" in missing
        assert "tavily_search" not in missing
    
    def test_validate_yaml_tools_handles_empty_tools(self):
        """validate_yaml_tools should handle roles with no tools."""
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        
        yaml_config = {
            "roles": {
                "researcher": {
                    "goal": "Research things"
                    # No tools field
                }
            }
        }
        
        missing = resolver.validate_yaml_tools(yaml_config)
        assert missing == []


class TestToolResolverPerformance:
    """Test performance characteristics."""
    
    def test_lazy_loading_no_import_overhead(self):
        """Importing ToolResolver should not import heavy dependencies."""
        start = time.time()
        from praisonai.tool_resolver import ToolResolver  # noqa: F401
        import_time = time.time() - start
        
        # Import should be fast (< 100ms)
        assert import_time < 0.1, f"Import took {import_time}s, expected < 0.1s"
    
    def test_resolve_caches_local_tools(self, tmp_path, monkeypatch):
        """Resolver should cache local tools.py to avoid repeated file reads."""
        tools_py = tmp_path / "tools.py"
        tools_py.write_text('''
def cached_tool() -> str:
    return "cached"
''')
        
        monkeypatch.chdir(tmp_path)
        
        from praisonai.tool_resolver import ToolResolver
        resolver = ToolResolver()
        
        # First call loads from file
        tool1 = resolver.resolve("cached_tool")
        # Second call should use cache
        tool2 = resolver.resolve("cached_tool")
        
        assert tool1 is tool2  # Same object (cached)


class TestConvenienceFunctions:
    """Test module-level convenience functions."""
    
    def test_resolve_tool_function(self):
        """resolve_tool() convenience function should work."""
        from praisonai.tool_resolver import resolve_tool
        tool = resolve_tool("tavily_search")
        assert tool is not None
        assert callable(tool)
    
    def test_resolve_tools_function(self):
        """resolve_tools() convenience function should work."""
        from praisonai.tool_resolver import resolve_tools
        tools = resolve_tools(["tavily_search", "internet_search"])
        assert len(tools) == 2
    
    def test_list_available_tools_function(self):
        """list_available_tools() convenience function should work."""
        from praisonai.tool_resolver import list_available_tools
        available = list_available_tools()
        assert isinstance(available, dict)
        assert "tavily_search" in available
    
    def test_has_tool_function(self):
        """has_tool() convenience function should work."""
        from praisonai.tool_resolver import has_tool
        assert has_tool("tavily_search") is True
        assert has_tool("nonexistent_xyz") is False
