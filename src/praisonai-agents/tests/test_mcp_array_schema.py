"""Test MCP array schema generation and fixing."""
import unittest
from unittest.mock import Mock, AsyncMock
import asyncio
import json
from praisonaiagents.mcp.mcp_sse import SSEMCPTool, SSEMCPClient


class TestMCPArraySchema(unittest.TestCase):
    """Test that MCP tools properly handle array schemas."""
    
    def test_array_schema_fix(self):
        """Test that array schemas get 'items' property added."""
        # Create a mock session
        mock_session = Mock()
        
        # Create a tool with array parameter missing 'items'
        input_schema = {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    # Missing 'items' - this should be added by _fix_array_schemas
                    "description": "Array of file paths"
                },
                "format": {
                    "type": "string",
                    "description": "Output format"
                }
            },
            "required": ["paths"]
        }
        
        # Create SSEMCPTool
        tool = SSEMCPTool(
            name="read_multiple_files",
            description="Read multiple files",
            session=mock_session,
            input_schema=input_schema
        )
        
        # Convert to OpenAI format
        openai_tool = tool.to_openai_tool()
        
        # Check that the array schema now has 'items'
        self.assertIn("items", openai_tool["function"]["parameters"]["properties"]["paths"])
        self.assertEqual(openai_tool["function"]["parameters"]["properties"]["paths"]["items"], {"type": "string"})
        
        # Verify the full structure
        expected_schema = {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},  # This should be added
                    "description": "Array of file paths"
                },
                "format": {
                    "type": "string",
                    "description": "Output format"
                }
            },
            "required": ["paths"]
        }
        
        self.assertEqual(openai_tool["function"]["parameters"], expected_schema)
        
    def test_nested_array_schema_fix(self):
        """Test that nested array schemas also get fixed."""
        mock_session = Mock()
        
        # Create a more complex schema with nested arrays
        input_schema = {
            "type": "object",
            "properties": {
                "files": {
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            # Missing 'items'
                        },
                        "extensions": {
                            "type": "array",
                            # Missing 'items'
                        }
                    }
                }
            }
        }
        
        tool = SSEMCPTool(
            name="complex_tool",
            description="Complex tool with nested arrays",
            session=mock_session,
            input_schema=input_schema
        )
        
        openai_tool = tool.to_openai_tool()
        
        # Check nested arrays have 'items'
        files_props = openai_tool["function"]["parameters"]["properties"]["files"]["properties"]
        self.assertIn("items", files_props["paths"])
        self.assertIn("items", files_props["extensions"])
        
    def test_array_with_existing_items(self):
        """Test that existing 'items' properties are preserved."""
        mock_session = Mock()
        
        input_schema = {
            "type": "object",
            "properties": {
                "numbers": {
                    "type": "array",
                    "items": {"type": "integer"},  # Already has items
                    "description": "Array of numbers"
                }
            }
        }
        
        tool = SSEMCPTool(
            name="number_tool",
            description="Tool with properly defined array",
            session=mock_session,
            input_schema=input_schema
        )
        
        openai_tool = tool.to_openai_tool()
        
        # Check that existing items are preserved
        self.assertEqual(
            openai_tool["function"]["parameters"]["properties"]["numbers"]["items"],
            {"type": "integer"}
        )
        
    def test_sse_client_to_openai_tool(self):
        """Test that SSEMCPClient.to_openai_tool returns list of fixed tools."""
        # Mock the SSEMCPClient without actual initialization
        client = SSEMCPClient.__new__(SSEMCPClient)
        client.tools = []
        
        # Add a mock tool with array schema issue
        mock_tool = Mock()
        mock_tool.to_openai_tool.return_value = {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "Test tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {"type": "string"}  # Fixed
                        }
                    }
                }
            }
        }
        
        client.tools.append(mock_tool)
        
        # Test that to_openai_tool returns the list
        result = client.to_openai_tool()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["function"]["name"], "test_tool")


if __name__ == "__main__":
    unittest.main()