"""
Tests for enhanced --auto and --init modes with dynamic tool discovery.
"""
import pytest
from unittest.mock import patch, MagicMock
import os
import sys

# Add the praisonai package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TestToolDiscovery:
    """Tests for dynamic tool discovery functionality."""
    
    def test_get_all_available_tools_returns_dict(self):
        """Test that get_all_available_tools returns a dictionary."""
        from praisonai.auto import get_all_available_tools
        tools = get_all_available_tools()
        assert isinstance(tools, dict)
    
    def test_get_all_available_tools_has_categories(self):
        """Test that tools are organized by category."""
        from praisonai.auto import get_all_available_tools
        tools = get_all_available_tools()
        # Should have categories like 'file', 'web', 'data', etc.
        assert len(tools) > 0
        for category, tool_list in tools.items():
            assert isinstance(category, str)
            assert isinstance(tool_list, list)
    
    def test_get_tools_for_task_returns_list(self):
        """Test that get_tools_for_task returns appropriate tools."""
        from praisonai.auto import get_tools_for_task
        tools = get_tools_for_task("Search the web for information")
        assert isinstance(tools, list)
    
    def test_get_tools_for_task_web_search(self):
        """Test that web search tasks get search tools."""
        from praisonai.auto import get_tools_for_task
        tools = get_tools_for_task("Search the internet for AI news")
        tool_names = [t if isinstance(t, str) else t.__name__ for t in tools]
        # Should include search-related tools
        assert any('search' in name.lower() for name in tool_names)
    
    def test_get_tools_for_task_file_operations(self):
        """Test that file tasks get file tools."""
        from praisonai.auto import get_tools_for_task
        tools = get_tools_for_task("Read and analyze the config file")
        tool_names = [t if isinstance(t, str) else t.__name__ for t in tools]
        # Should include file-related tools
        assert any('file' in name.lower() or 'read' in name.lower() for name in tool_names)
    
    def test_get_tools_for_task_code_execution(self):
        """Test that code tasks get execution tools."""
        from praisonai.auto import get_tools_for_task
        tools = get_tools_for_task("Execute Python code to analyze data")
        tool_names = [t if isinstance(t, str) else t.__name__ for t in tools]
        # Should include code execution tools
        assert any('execute' in name.lower() or 'code' in name.lower() or 'command' in name.lower() for name in tool_names)


class TestEnhancedAutoGenerator:
    """Tests for enhanced AutoGenerator with tool discovery."""
    
    def test_enhanced_generator_has_tool_discovery(self):
        """Test that EnhancedAutoGenerator has tool discovery method."""
        from praisonai.auto import AutoGenerator
        generator = AutoGenerator(topic="Test task", framework="praisonai")
        assert hasattr(generator, 'discover_tools_for_topic')
    
    def test_analyze_task_complexity(self):
        """Test task complexity analysis."""
        from praisonai.auto import BaseAutoGenerator
        
        # Simple task
        assert BaseAutoGenerator.analyze_complexity("Write a haiku") == 'simple'
        
        # Complex task
        assert BaseAutoGenerator.analyze_complexity("Comprehensive multi-step analysis") == 'complex'
        
        # Moderate task (needs a keyword that's not in simple or complex lists)
        assert BaseAutoGenerator.analyze_complexity("Analyze the market trends") == 'moderate'
    
    def test_recommend_agent_count(self):
        """Test agent count recommendation based on complexity."""
        from praisonai.auto import recommend_agent_count
        
        # Simple tasks should get 1 agent
        assert recommend_agent_count("Write a poem") == 1
        
        # Complex tasks should get more agents
        count = recommend_agent_count("Comprehensive research and analysis with multiple perspectives")
        assert count >= 2


class TestToolCategoryMapping:
    """Tests for tool category mapping."""
    
    def test_tool_categories_defined(self):
        """Test that tool categories are properly defined."""
        from praisonai.auto import TOOL_CATEGORIES
        assert isinstance(TOOL_CATEGORIES, dict)
        assert 'web_search' in TOOL_CATEGORIES
        assert 'file_operations' in TOOL_CATEGORIES
        assert 'code_execution' in TOOL_CATEGORIES
    
    def test_task_keywords_mapping(self):
        """Test that task keywords map to tool categories."""
        from praisonai.auto import TASK_KEYWORD_TO_TOOLS
        assert isinstance(TASK_KEYWORD_TO_TOOLS, dict)
        # Keywords like 'search', 'find', 'look up' should map to web search
        assert 'search' in TASK_KEYWORD_TO_TOOLS or any('search' in k for k in TASK_KEYWORD_TO_TOOLS)


class TestEnhancedYAMLGeneration:
    """Tests for enhanced YAML generation."""
    
    def test_generated_yaml_includes_tools(self):
        """Test that generated YAML includes appropriate tools."""
        from praisonai.auto import AutoGenerator
        
        # Test that the generator has tool discovery capability
        generator = AutoGenerator(
            topic="Search the web for AI news and write a summary",
            agent_file="test_agents.yaml",
            framework="praisonai"
        )
        
        # Verify tool discovery works
        tools = generator.discover_tools_for_topic()
        assert isinstance(tools, list)
        assert len(tools) > 0
        # Should include search tools for this task
        tool_names = [t if isinstance(t, str) else str(t) for t in tools]
        assert any('search' in name.lower() for name in tool_names)


class TestIntegrationWithAgentsTools:
    """Tests for integration with praisonaiagents.tools."""
    
    def test_can_import_praisonaiagents_tools(self):
        """Test that we can import tools from praisonaiagents."""
        try:
            from praisonaiagents.tools import TOOL_MAPPINGS
            assert isinstance(TOOL_MAPPINGS, dict)
            assert len(TOOL_MAPPINGS) > 0
        except ImportError:
            pytest.skip("praisonaiagents not installed")
    
    def test_tool_mappings_include_core_tools(self):
        """Test that core tools are available."""
        try:
            from praisonaiagents.tools import TOOL_MAPPINGS
            core_tools = ['read_file', 'write_file', 'execute_command', 'internet_search']
            for tool in core_tools:
                assert tool in TOOL_MAPPINGS, f"Core tool {tool} not found"
        except ImportError:
            pytest.skip("praisonaiagents not installed")
