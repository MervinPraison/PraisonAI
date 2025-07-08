#!/usr/bin/env python3
"""Test script to verify MCP schema fixes."""

import os
import sys
from pathlib import Path

# Add the source directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "src" / "praisonai-agents"))

from praisonaiagents import Agent, MCP

def test_basic_agent_with_tool():
    """Test basic agent with a simple tool."""
    print("Testing basic agent with tool...")
    
    def get_weather(location: str) -> str:
        """Get the weather for a location."""
        return f"The weather in {location} is sunny."
    
    try:
        agent = Agent(
            instructions="You are a helpful assistant",
            llm="gpt-4o-mini",
            tools=[get_weather]
        )
        print("✅ Basic agent with tool created successfully")
        
        # Test tool definition generation
        tool_def = agent._generate_tool_definition("get_weather")
        print(f"Tool definition: {tool_def}")
        
        if tool_def and "function" in tool_def and "name" in tool_def["function"]:
            print("✅ Tool definition generated correctly")
        else:
            print("❌ Tool definition generation failed")
            
    except Exception as e:
        print(f"❌ Basic agent test failed: {e}")

def test_mcp_filesystem_agent():
    """Test MCP agent with filesystem server."""
    print("\nTesting MCP filesystem agent...")
    
    # Define allowed directories
    allowed_dirs = [
        os.getcwd(),  # Current directory
    ]
    
    try:
        filesystem_agent = Agent(
            instructions="""You are a helpful assistant that can interact with the filesystem.
            Use the available tools when relevant to manage files and directories.""",
            llm="gpt-4o-mini",
            tools=MCP(
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem"] + allowed_dirs
            )
        )
        print("✅ MCP filesystem agent created successfully")
        
        # Check if tools were properly formatted
        formatted_tools = filesystem_agent._format_tools_for_completion()
        print(f"Number of tools formatted: {len(formatted_tools)}")
        
        # Check for array parameters with items property
        has_array_with_items = False
        for tool in formatted_tools:
            if "function" in tool and "parameters" in tool["function"]:
                params = tool["function"]["parameters"]
                if "properties" in params:
                    for prop_name, prop_schema in params["properties"].items():
                        if prop_schema.get("type") == "array" and "items" in prop_schema:
                            has_array_with_items = True
                            print(f"✅ Found array parameter '{prop_name}' with items property")
                            
        if has_array_with_items:
            print("✅ Array parameters have required 'items' property")
        else:
            print("⚠️  No array parameters found or missing 'items' property")
            
    except Exception as e:
        print(f"❌ MCP filesystem agent test failed: {e}")
        import traceback
        traceback.print_exc()

def test_array_parameter_function():
    """Test function with array parameter."""
    print("\nTesting function with array parameter...")
    
    def process_files(paths: list) -> str:
        """Process multiple files.
        
        Args:
            paths: List of file paths to process
        """
        return f"Processed {len(paths)} files"
    
    try:
        agent = Agent(
            instructions="You are a file processor",
            llm="gpt-4o-mini",
            tools=[process_files]
        )
        print("✅ Agent with array parameter function created")
        
        # Get tool definition
        tool_def = agent._generate_tool_definition("process_files")
        
        if tool_def and "function" in tool_def:
            params = tool_def["function"].get("parameters", {})
            props = params.get("properties", {})
            paths_param = props.get("paths", {})
            
            if paths_param.get("type") == "array" and "items" in paths_param:
                print("✅ Array parameter has required 'items' property")
                print(f"   Array items type: {paths_param['items'].get('type')}")
            else:
                print("❌ Array parameter missing 'items' property")
                
    except Exception as e:
        print(f"❌ Array parameter test failed: {e}")

if __name__ == "__main__":
    print("=== MCP Schema Fix Test Suite ===\n")
    
    test_basic_agent_with_tool()
    test_mcp_filesystem_agent()
    test_array_parameter_function()
    
    print("\n=== Test Summary ===")
    print("The fixes address:")
    print("1. Missing _generate_tool_definition method in Agent class")
    print("2. Array parameters missing 'items' property in schema")
    print("3. Proper handling of MCP tools returning multiple tools")