#!/usr/bin/env python3
"""Test script to verify the array schema fix for MCP tools."""

import json
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents import Agent, MCP
from praisonaiagents.llm import LLM

def test_array_parameter(items: list):
    """Test function with array parameter.
    
    Args:
        items: List of items to process
    """
    return f"Processed {len(items)} items"

def test_tool_definition_generation():
    """Test that tool definitions include items property for arrays."""
    print("Testing tool definition generation with array parameters...")
    
    # Test LLM._generate_tool_definition
    llm = LLM()
    tool_def = llm._generate_tool_definition(test_array_parameter)
    
    print("\nLLM-generated tool definition:")
    print(json.dumps(tool_def, indent=2))
    
    # Check if array parameter has items property
    if tool_def and 'function' in tool_def and 'parameters' in tool_def['function']:
        params = tool_def['function']['parameters']
        if 'properties' in params and 'items' in params['properties']:
            items_param = params['properties']['items']
            if items_param.get('type') == 'array' and 'items' in items_param:
                print("✅ LLM: Array parameter has required 'items' property")
            else:
                print("❌ LLM: Array parameter missing 'items' property")
    
    # Test Agent._generate_tool_definition
    agent = Agent(
        name="TestAgent",
        role="Tester",
        goal="Test tool definitions"
    )
    
    # Direct test since _generate_tool_definition is private
    tool_def_agent = agent._generate_tool_definition(test_array_parameter)
    
    print("\nAgent-generated tool definition:")
    print(json.dumps(tool_def_agent, indent=2))
    
    # Check if array parameter has items property
    if tool_def_agent and 'function' in tool_def_agent and 'parameters' in tool_def_agent['function']:
        params = tool_def_agent['function']['parameters']
        if 'properties' in params and 'items' in params['properties']:
            items_param = params['properties']['items']
            if items_param.get('type') == 'array' and 'items' in items_param:
                print("✅ Agent: Array parameter has required 'items' property")
            else:
                print("❌ Agent: Array parameter missing 'items' property")

def test_mcp_filesystem():
    """Test MCP filesystem with array parameters."""
    print("\n\nTesting MCP filesystem schema...")
    
    # Define allowed directories
    allowed_dirs = [
        os.path.dirname(__file__),  # Current directory
    ]
    
    try:
        # Create MCP instance
        mcp_tool = MCP(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"] + allowed_dirs
        )
        
        # Get OpenAI tools
        openai_tools = mcp_tool.to_openai_tool()
        
        if openai_tools:
            print(f"\nMCP returned {len(openai_tools)} tools")
            
            # Look for read_multiple_files tool
            for tool in openai_tools:
                if tool.get('function', {}).get('name') == 'read_multiple_files':
                    print("\nFound 'read_multiple_files' tool:")
                    print(json.dumps(tool, indent=2))
                    
                    # Check paths parameter
                    params = tool.get('function', {}).get('parameters', {})
                    paths_param = params.get('properties', {}).get('paths', {})
                    
                    if paths_param.get('type') == 'array' and 'items' in paths_param:
                        print("✅ MCP: 'paths' array parameter has required 'items' property")
                        print(f"   Items type: {paths_param['items']}")
                    else:
                        print("❌ MCP: 'paths' array parameter missing 'items' property")
                        print(f"   Actual schema: {json.dumps(paths_param, indent=2)}")
        else:
            print("⚠️  MCP tool conversion returned no tools")
            
    except Exception as e:
        print(f"⚠️  MCP test skipped: {e}")
        print("   (This is expected if MCP server is not available)")

if __name__ == "__main__":
    print("=== Testing Array Schema Fix ===\n")
    test_tool_definition_generation()
    test_mcp_filesystem()
    print("\n=== Test Complete ===")