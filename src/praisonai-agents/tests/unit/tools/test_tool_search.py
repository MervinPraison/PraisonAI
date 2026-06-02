"""
Unit tests for Tool Search functionality.

Tests core tool search components including:
- ToolSearchConfig
- Tool classification 
- BM25 search
- Bridge tool schemas
- Assembly logic
"""

import pytest
from praisonaiagents.tools.tool_search import (
    ToolSearchConfig, classify_tools, search_catalog, bridge_tool_schemas,
    assemble_tool_defs, dispatch_tool_search, dispatch_tool_describe,
    resolve_underlying_call, PRAISONAI_CORE_TOOLS,
    estimate_tool_schema_tokens, should_defer_tools
)

class TestToolSearchConfig:
    """Test ToolSearchConfig creation and validation."""
    
    def test_default_config(self):
        """Test default configuration."""
        config = ToolSearchConfig()
        assert config.enabled == "auto"
        assert config.threshold_pct == 10.0
        assert config.search_default_limit == 5
        assert config.max_search_limit == 20
        assert config.core_tools is None
    
    def test_from_raw_bool(self):
        """Test creating config from boolean values."""
        config_true = ToolSearchConfig.from_raw(True)
        assert config_true.enabled == "on"
        
        config_false = ToolSearchConfig.from_raw(False)
        assert config_false.enabled == "off"
    
    def test_from_raw_string(self):
        """Test creating config from string values."""
        config_auto = ToolSearchConfig.from_raw("auto")
        assert config_auto.enabled == "auto"
        
        config_on = ToolSearchConfig.from_raw("on") 
        assert config_on.enabled == "on"
        
        config_off = ToolSearchConfig.from_raw("off")
        assert config_off.enabled == "off"
    
    def test_from_raw_dict(self):
        """Test creating config from dictionary."""
        config = ToolSearchConfig.from_raw({
            "enabled": "on",
            "threshold_pct": 15.0,
            "search_default_limit": 10
        })
        assert config.enabled == "on"
        assert config.threshold_pct == 15.0
        assert config.search_default_limit == 10
    
    def test_from_raw_invalid(self):
        """Test error handling for invalid inputs."""
        with pytest.raises(ValueError):
            ToolSearchConfig.from_raw("invalid")
        
        with pytest.raises(TypeError):
            ToolSearchConfig.from_raw(123)

class TestToolClassification:
    """Test tool classification into core vs deferrable."""
    
    def test_core_tool_classification(self):
        """Test that core tools are never deferred."""
        tool_defs = [
            {
                "type": "function",
                "function": {"name": "read_file", "description": "Read a file"}
            },
            {
                "type": "function", 
                "function": {"name": "search_web", "description": "Search the web"}
            }
        ]
        
        config = ToolSearchConfig()
        core_tools, deferrable_tools = classify_tools(tool_defs, config)
        
        assert len(core_tools) == 2
        assert len(deferrable_tools) == 0
        assert core_tools == tool_defs
    
    def test_mcp_tool_classification(self):
        """Test that MCP tools are marked as deferrable.""" 
        tool_defs = [
            {
                "type": "function",
                "function": {"name": "mcp_weather", "description": "Get weather"},
                "__praisonai_deferrable__": True
            },
            {
                "type": "function",
                "function": {"name": "read_file", "description": "Read a file"}
            }
        ]
        
        config = ToolSearchConfig()
        core_tools, deferrable_tools = classify_tools(tool_defs, config)
        
        assert len(core_tools) == 1
        assert len(deferrable_tools) == 1
        assert core_tools[0]["function"]["name"] == "read_file"
        assert deferrable_tools[0]["function"]["name"] == "mcp_weather"
    
    def test_unknown_tool_stays_visible(self):
        """Test that unknown tools stay visible (design invariant #2)."""
        tool_defs = [
            {
                "type": "function",
                "function": {"name": "unknown_tool", "description": "Unknown tool"}
            }
        ]
        
        config = ToolSearchConfig()
        core_tools, deferrable_tools = classify_tools(tool_defs, config)
        
        # Unknown tools should stay in core (visible)
        assert len(core_tools) == 1
        assert len(deferrable_tools) == 0
        assert core_tools[0]["function"]["name"] == "unknown_tool"

class TestBM25Search:
    """Test BM25 search functionality."""
    
    def test_empty_search(self):
        """Test search with empty inputs."""
        result = search_catalog([], "test query")
        assert result == []
        
        result = search_catalog([{"type": "function", "function": {"name": "test"}}], "")
        assert result == []
    
    def test_simple_search(self):
        """Test basic search functionality."""
        deferrable_tools = [
            {
                "type": "function",
                "function": {
                    "name": "weather_tool",
                    "description": "Get current weather information"
                }
            },
            {
                "type": "function", 
                "function": {
                    "name": "stock_tool",
                    "description": "Get stock market data"
                }
            }
        ]
        
        results = search_catalog(deferrable_tools, "weather", limit=10)
        assert len(results) >= 1
        assert any("weather_tool" in r["name"] for r in results)
        
        results = search_catalog(deferrable_tools, "stock", limit=10)
        assert len(results) >= 1
        assert any("stock_tool" in r["name"] for r in results)

class TestBridgeTools:
    """Test bridge tool schemas and assembly."""
    
    def test_bridge_schemas(self):
        """Test bridge tool schema generation."""
        schemas = bridge_tool_schemas()
        assert len(schemas) == 3
        
        tool_names = {schema["function"]["name"] for schema in schemas}
        assert tool_names == {"tool_search", "tool_describe", "tool_call"}
        
        # Validate schema structure
        for schema in schemas:
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "description" in schema["function"] 
            assert "parameters" in schema["function"]
    
    def test_assemble_disabled(self):
        """Test assembly when tool search is disabled."""
        tool_defs = [
            {"type": "function", "function": {"name": "test_tool", "description": "Test"}}
        ]
        
        config = ToolSearchConfig(enabled="off")
        assembled, metadata = assemble_tool_defs(tool_defs, config)
        
        assert assembled == tool_defs
        assert metadata["bridge_mode"] is False
        assert metadata["deferred_count"] == 0
    
    def test_assemble_no_deferrable_tools(self):
        """Test assembly when no tools are deferrable."""
        tool_defs = [
            {"type": "function", "function": {"name": "read_file", "description": "Read file"}}
        ]
        
        config = ToolSearchConfig(enabled="on")
        assembled, metadata = assemble_tool_defs(tool_defs, config)
        
        # Should return original tools since nothing to defer
        assert assembled == tool_defs
        assert metadata["bridge_mode"] is False
    
    def test_assemble_with_deferrable_tools(self):
        """Test assembly with deferrable tools."""
        tool_defs = [
            {"type": "function", "function": {"name": "read_file", "description": "Read file"}},
            {
                "type": "function", 
                "function": {"name": "mcp_weather", "description": "Get weather"},
                "__praisonai_deferrable__": True
            }
        ]
        
        config = ToolSearchConfig(enabled="on")
        assembled, metadata = assemble_tool_defs(tool_defs, config)
        
        # Should have core tool + 3 bridge tools
        assert len(assembled) == 4
        assert metadata["bridge_mode"] is True
        assert metadata["deferred_count"] == 1
        assert len(metadata["catalog"]) == 1
        
        # Verify core tool remains
        core_tool_names = {t["function"]["name"] for t in assembled if t["function"]["name"] != "tool_search" and t["function"]["name"] != "tool_describe" and t["function"]["name"] != "tool_call"}
        assert "read_file" in core_tool_names

class TestBridgeDispatchers:
    """Test bridge tool dispatch handlers."""
    
    def test_tool_search_dispatch(self):
        """Test tool_search bridge dispatch."""
        deferrable_tools = [
            {
                "type": "function",
                "function": {
                    "name": "weather_tool", 
                    "description": "Get weather information"
                }
            }
        ]
        
        config = ToolSearchConfig()
        result = dispatch_tool_search("weather", 5, deferrable_tools, config)
        
        assert "query" in result
        assert "results" in result
        assert "total_available" in result
        assert result["query"] == "weather"
        assert result["total_available"] == 1
    
    def test_tool_describe_dispatch(self):
        """Test tool_describe bridge dispatch."""
        deferrable_tools = [
            {
                "type": "function",
                "function": {
                    "name": "weather_tool",
                    "description": "Get weather information"
                }
            }
        ]
        
        result = dispatch_tool_describe("weather_tool", deferrable_tools)
        
        assert "tool_name" in result
        assert "found" in result
        assert result["found"] is True
        assert result["tool_name"] == "weather_tool"
        assert "schema" in result
    
    def test_tool_describe_not_found(self):
        """Test tool_describe for non-existent tool."""
        result = dispatch_tool_describe("nonexistent_tool", [])
        
        assert "tool_name" in result
        assert "found" in result
        assert result["found"] is False
        assert "error" in result

class TestToolCallUnwrapping:
    """Test tool_call bridge unwrapping."""
    
    def test_resolve_underlying_call(self):
        """Test unwrapping tool_call bridge."""
        # Normal tool call - should pass through
        name, args = resolve_underlying_call("normal_tool", {"arg1": "value1"})
        assert name == "normal_tool"
        assert args == {"arg1": "value1"}
        
        # Bridge tool call - should unwrap
        bridge_args = {
            "tool_name": "real_tool",
            "tool_args": {"param1": "test"}
        }
        name, args = resolve_underlying_call("tool_call", bridge_args)
        assert name == "real_tool"
        assert args == {"param1": "test"}
    
    def test_resolve_missing_tool_name(self):
        """Test error handling for missing tool_name."""
        with pytest.raises(ValueError, match="tool_call requires 'tool_name' parameter"):
            resolve_underlying_call("tool_call", {"tool_args": {}})

class TestTokenEstimation:
    """Test token estimation and threshold logic."""
    
    def test_estimate_tool_schema_tokens(self):
        """Test token estimation for tool schemas.""" 
        tool_defs = [
            {
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool with parameters",
                    "parameters": {
                        "type": "object",
                        "properties": {"param1": {"type": "string"}}
                    }
                }
            }
        ]
        
        tokens = estimate_tool_schema_tokens(tool_defs)
        assert tokens > 0
        assert isinstance(tokens, int)
    
    def test_should_defer_tools(self):
        """Test deferral threshold logic."""
        # Create some dummy deferrable tools
        deferrable_tools = [
            {
                "type": "function",
                "function": {"name": f"tool_{i}", "description": "Test tool"}
            } 
            for i in range(10)
        ]
        
        # Test with disabled config
        config_off = ToolSearchConfig(enabled="off")
        assert should_defer_tools(deferrable_tools, config_off, 20000) is False
        
        # Test with on config 
        config_on = ToolSearchConfig(enabled="on")
        assert should_defer_tools(deferrable_tools, config_on, 20000) is True
        
        # Test auto mode with high threshold (shouldn't defer)
        config_auto_high = ToolSearchConfig(enabled="auto", threshold_pct=90)
        assert should_defer_tools(deferrable_tools, config_auto_high, 20000) is False
        
        # Test auto mode with low threshold (should defer)
        config_auto_low = ToolSearchConfig(enabled="auto", threshold_pct=1)  
        assert should_defer_tools(deferrable_tools, config_auto_low, 20000) is True

class TestCoreToolsInvariant:
    """Test that core tools never defer."""
    
    def test_core_tools_constant(self):
        """Test that PRAISONAI_CORE_TOOLS is properly defined."""
        assert isinstance(PRAISONAI_CORE_TOOLS, frozenset)
        assert len(PRAISONAI_CORE_TOOLS) > 0
        
        # Check some expected core tools
        expected_core = {"read_file", "execute_command", "search_web", "clarify"}
        assert expected_core.issubset(PRAISONAI_CORE_TOOLS)
    
    def test_core_tools_never_deferred(self):
        """Test that core tools are never put in deferrable category."""
        # Create tools that are marked as deferrable but are actually core tools
        tool_defs = []
        for tool_name in list(PRAISONAI_CORE_TOOLS)[:5]:  # Test first 5 core tools
            tool_defs.append({
                "type": "function",
                "function": {"name": tool_name, "description": f"Test {tool_name}"},
                "__praisonai_deferrable__": True  # Try to mark as deferrable
            })
        
        config = ToolSearchConfig()
        core_tools, deferrable_tools = classify_tools(tool_defs, config)
        
        # All should end up in core tools despite the deferrable marker
        assert len(core_tools) == 5
        assert len(deferrable_tools) == 0