"""Test tool schema parity and OpenAI compatibility.

This module tests the fixes for issue #1696 to ensure BaseTool ↔ OpenAI-compatible
tool schema parity in chat/agent dispatch.
"""

import pytest
import json
from typing import Any, Dict, List
from praisonaiagents.tools.base import BaseTool, ToolValidationError, validate_tool_schema_consistency
from praisonaiagents.tools.decorator import tool, FunctionTool


class MockTool(BaseTool):
    """A simple mock tool for testing."""
    
    name = "mock_tool"
    description = "A mock tool for testing"
    
    def run(self, query: str, count: int = 1) -> str:
        return f"Mock result for {query} (count: {count})"


class TestBasicToolSchemaValidation:
    """Test basic tool schema validation and OpenAI compatibility."""
    
    def test_base_tool_schema_structure(self):
        """Test that BaseTool generates correct OpenAI schema structure."""
        tool = MockTool()
        schema = tool.get_schema()
        
        # Validate top-level structure
        assert isinstance(schema, dict)
        assert schema["type"] == "function"
        assert "function" in schema
        
        # Validate function structure
        func = schema["function"]
        assert func["name"] == "mock_tool"
        assert func["description"] == "A mock tool for testing"
        assert "parameters" in func
        
        # Validate parameters structure
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params
        
        # Validate specific properties
        props = params["properties"]
        assert "query" in props
        assert "count" in props
        assert props["query"]["type"] == "string"
        assert props["count"]["type"] == "integer"
        
        # Validate required fields
        assert "query" in params["required"]
        assert "count" not in params["required"]  # Has default value
    
    def test_tool_schema_json_serialization(self):
        """Test that tool schemas can be JSON serialized (round-trip test)."""
        tool = MockTool()
        schema = tool.get_schema()
        
        # Should serialize without errors
        serialized = json.dumps(schema)
        assert isinstance(serialized, str)
        
        # Should deserialize back to same structure
        deserialized = json.loads(serialized)
        assert deserialized == schema
    
    def test_tool_validation_passes(self):
        """Test that valid tools pass validation."""
        tool = MockTool()
        
        # Basic validation should pass
        assert tool.validate() == True
        
        # Round-trip validation should pass
        assert tool.validate_schema_roundtrip() == True
    
    def test_function_tool_schema_parity(self):
        """Test that @tool decorated functions have same schema structure."""
        @tool
        def test_function(query: str, count: int = 1) -> str:
            """A test function for schema validation."""
            return f"Result for {query} (count: {count})"
        
        schema = test_function.get_schema()
        
        # Should have same structure as BaseTool
        assert schema["type"] == "function"
        func = schema["function"]
        assert func["name"] == "test_function"
        assert "parameters" in func
        
        params = func["parameters"]
        assert params["type"] == "object"
        assert "properties" in params
        assert "required" in params


class TestToolSchemaValidationErrors:
    """Test that validation catches schema errors."""
    
    def test_invalid_tool_missing_properties(self):
        """Test validation fails for tools with invalid parameters."""
        
        class BadTool(BaseTool):
            name = "bad_tool"
            description = "Bad tool"
            parameters = {"type": "object"}  # Missing properties
            
            def run(self, query: str) -> str:
                return query
        
        tool = BadTool()
        with pytest.raises(ToolValidationError, match="must have a 'properties' field"):
            tool.validate()
    
    def test_invalid_tool_missing_type(self):
        """Test validation fails for tools with missing type."""
        
        class BadTool(BaseTool):
            name = "bad_tool"
            description = "Bad tool"
            parameters = {"properties": {}}  # Missing type
            
            def run(self, query: str) -> str:
                return query
        
        tool = BadTool()
        with pytest.raises(ToolValidationError, match="must have a 'type' field"):
            tool.validate()


class TestToolListValidation:
    """Test validation of tool lists for consistency."""
    
    def test_valid_tool_list(self):
        """Test that valid tool lists pass consistency checks."""
        @tool
        def tool_one(x: str) -> str:
            """First tool."""
            return x
            
        @tool  
        def tool_two(y: int) -> int:
            """Second tool."""
            return y
        
        tool_three = MockTool()
        
        tools = [tool_one, tool_two, tool_three]
        
        # Should pass validation
        assert validate_tool_schema_consistency(tools) == True
    
    def test_duplicate_tool_names_error(self):
        """Test that duplicate tool names are caught."""
        @tool(name="duplicate_name")
        def tool_one(x: str) -> str:
            return x
            
        @tool(name="duplicate_name")  
        def tool_two(y: int) -> int:
            return y
        
        tools = [tool_one, tool_two]
        
        with pytest.raises(ToolValidationError, match="Duplicate tool name"):
            validate_tool_schema_consistency(tools)
    
    def test_empty_tool_list(self):
        """Test that empty tool lists are valid."""
        assert validate_tool_schema_consistency([]) == True


class TestRealAgenticScenario:
    """Test real agentic scenarios to ensure end-to-end compatibility."""
    
    def test_tool_schema_agent_integration(self):
        """Test that tools work with agent in real scenario."""
        from praisonaiagents import Agent
        
        @tool
        def echo_tool(message: str) -> str:
            """Echo the input message."""
            return f"Echo: {message}"
        
        # Create agent with tool - should not raise validation errors
        agent = Agent(
            name="test_agent", 
            instructions="You are a helpful assistant",
            tools=[echo_tool]
        )
        
        # Schema should be valid for LLM use
        schema = echo_tool.get_schema()
        assert schema["type"] == "function"
        
        # Should be JSON serializable 
        json.dumps(schema)
        
        # Agent should format tools properly
        formatted_tools = agent._format_tools_for_completion(agent.tools)
        assert len(formatted_tools) == 1
        assert formatted_tools[0]["type"] == "function"
        
        print("✅ Real agentic test passed: Tool schema integration works end-to-end")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])