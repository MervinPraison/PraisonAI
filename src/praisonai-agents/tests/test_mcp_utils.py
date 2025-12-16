"""Tests for MCP utility functions - TDD approach.

These tests define the expected behavior of mcp_utils module.
"""

import pytest
from typing import Optional, List, Dict, Any


class TestFunctionToMCPSchema:
    """Test function_to_mcp_schema() converts Python functions to MCP tool schemas."""
    
    def test_simple_function_with_string_param(self):
        """Test conversion of simple function with string parameter."""
        from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
        
        def search(query: str) -> str:
            """Search the web for information."""
            return f"Results for {query}"
        
        schema = function_to_mcp_schema(search)
        
        assert schema["name"] == "search"
        assert schema["description"] == "Search the web for information."
        assert schema["inputSchema"]["type"] == "object"
        assert "query" in schema["inputSchema"]["properties"]
        assert schema["inputSchema"]["properties"]["query"]["type"] == "string"
        assert "query" in schema["inputSchema"]["required"]
    
    def test_function_with_multiple_params(self):
        """Test function with multiple parameters of different types."""
        from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
        
        def search(query: str, max_results: int, include_images: bool) -> Dict[str, Any]:
            """Search with options."""
            return {}
        
        schema = function_to_mcp_schema(search)
        
        assert schema["name"] == "search"
        props = schema["inputSchema"]["properties"]
        assert props["query"]["type"] == "string"
        assert props["max_results"]["type"] == "integer"
        assert props["include_images"]["type"] == "boolean"
        assert set(schema["inputSchema"]["required"]) == {"query", "max_results", "include_images"}
    
    def test_function_with_optional_params(self):
        """Test function with optional parameters (defaults)."""
        from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
        
        def search(query: str, max_results: int = 10, include_images: bool = False) -> str:
            """Search with optional params."""
            return ""
        
        schema = function_to_mcp_schema(search)
        
        # Only required params should be in required list
        assert schema["inputSchema"]["required"] == ["query"]
        # All params should still be in properties
        assert "max_results" in schema["inputSchema"]["properties"]
        assert "include_images" in schema["inputSchema"]["properties"]
    
    def test_function_with_list_param(self):
        """Test function with list parameter."""
        from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
        
        def process(items: List[str]) -> str:
            """Process a list of items."""
            return ""
        
        schema = function_to_mcp_schema(process)
        
        assert schema["inputSchema"]["properties"]["items"]["type"] == "array"
        assert schema["inputSchema"]["properties"]["items"]["items"]["type"] == "string"
    
    def test_function_with_dict_param(self):
        """Test function with dict parameter."""
        from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
        
        def process(data: Dict[str, Any]) -> str:
            """Process data dictionary."""
            return ""
        
        schema = function_to_mcp_schema(process)
        
        assert schema["inputSchema"]["properties"]["data"]["type"] == "object"
    
    def test_function_with_optional_type(self):
        """Test function with Optional type hint."""
        from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
        
        def search(query: str, category: Optional[str] = None) -> str:
            """Search with optional category."""
            return ""
        
        schema = function_to_mcp_schema(search)
        
        assert "category" in schema["inputSchema"]["properties"]
        assert "category" not in schema["inputSchema"]["required"]
    
    def test_function_without_docstring(self):
        """Test function without docstring uses function name as description."""
        from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
        
        def my_tool(x: str) -> str:
            return x
        
        schema = function_to_mcp_schema(my_tool)
        
        assert schema["name"] == "my_tool"
        assert schema["description"] == "my_tool"  # Falls back to name
    
    def test_async_function(self):
        """Test async function is handled correctly."""
        from praisonaiagents.mcp.mcp_utils import function_to_mcp_schema
        
        async def async_search(query: str) -> str:
            """Async search function."""
            return ""
        
        schema = function_to_mcp_schema(async_search)
        
        assert schema["name"] == "async_search"
        assert schema["description"] == "Async search function."


class TestGetToolMetadata:
    """Test get_tool_metadata() extracts metadata from functions."""
    
    def test_extracts_name(self):
        """Test name extraction."""
        from praisonaiagents.mcp.mcp_utils import get_tool_metadata
        
        def my_tool(x: str) -> str:
            """Tool description."""
            return x
        
        metadata = get_tool_metadata(my_tool)
        assert metadata["name"] == "my_tool"
    
    def test_extracts_description_from_docstring(self):
        """Test description extraction from docstring."""
        from praisonaiagents.mcp.mcp_utils import get_tool_metadata
        
        def my_tool(x: str) -> str:
            """This is the tool description.
            
            More details here.
            """
            return x
        
        metadata = get_tool_metadata(my_tool)
        assert metadata["description"] == "This is the tool description."
    
    def test_custom_name_attribute(self):
        """Test custom __mcp_name__ attribute is used."""
        from praisonaiagents.mcp.mcp_utils import get_tool_metadata
        
        def my_tool(x: str) -> str:
            """Description."""
            return x
        
        my_tool.__mcp_name__ = "custom_name"
        
        metadata = get_tool_metadata(my_tool)
        assert metadata["name"] == "custom_name"
    
    def test_custom_description_attribute(self):
        """Test custom __mcp_description__ attribute is used."""
        from praisonaiagents.mcp.mcp_utils import get_tool_metadata
        
        def my_tool(x: str) -> str:
            """Original docstring."""
            return x
        
        my_tool.__mcp_description__ = "Custom description"
        
        metadata = get_tool_metadata(my_tool)
        assert metadata["description"] == "Custom description"


class TestPythonTypeToJsonSchema:
    """Test Python type to JSON Schema conversion."""
    
    def test_basic_types(self):
        """Test basic Python types convert correctly."""
        from praisonaiagents.mcp.mcp_utils import python_type_to_json_schema
        
        assert python_type_to_json_schema(str) == {"type": "string"}
        assert python_type_to_json_schema(int) == {"type": "integer"}
        assert python_type_to_json_schema(float) == {"type": "number"}
        assert python_type_to_json_schema(bool) == {"type": "boolean"}
    
    def test_list_type(self):
        """Test List type converts to array."""
        from praisonaiagents.mcp.mcp_utils import python_type_to_json_schema
        
        result = python_type_to_json_schema(List[str])
        assert result["type"] == "array"
        assert result["items"]["type"] == "string"
    
    def test_dict_type(self):
        """Test Dict type converts to object."""
        from praisonaiagents.mcp.mcp_utils import python_type_to_json_schema
        
        result = python_type_to_json_schema(Dict[str, Any])
        assert result["type"] == "object"
    
    def test_optional_type(self):
        """Test Optional type is handled."""
        from praisonaiagents.mcp.mcp_utils import python_type_to_json_schema
        
        result = python_type_to_json_schema(Optional[str])
        assert result["type"] == "string"  # Optional just means nullable
    
    def test_any_type(self):
        """Test Any type converts to empty schema."""
        from praisonaiagents.mcp.mcp_utils import python_type_to_json_schema
        
        result = python_type_to_json_schema(Any)
        assert result == {}  # Any type = no constraints


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
