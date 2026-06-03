#!/usr/bin/env python3
"""
Debug script for dynamic schema override mechanism.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.tools import tool
from praisonaiagents.tools.registry import get_registry, get_tool_definitions

def test_schema_override(base_schema):
    """Test schema override function."""
    print(f"Override called with base schema: {base_schema}")
    schema = base_schema.copy()
    schema["function"]["description"] = "MODIFIED: " + schema["function"]["description"]
    return schema

@tool(name="test_tool", dynamic_schema_overrides=test_schema_override)
def test_function(query: str) -> str:
    """Test function for schema override."""
    return f"Result: {query}"

def main():
    print("=== Debug Dynamic Schema Override ===")
    
    # Get registry and check what's registered
    registry = get_registry()
    print(f"Registry: {registry}")
    print(f"Tools in registry: {registry.list_tools()}")
    
    # Get tool definitions
    definitions = get_tool_definitions()
    print(f"Number of tool definitions: {len(definitions)}")
    
    for i, defn in enumerate(definitions):
        print(f"Tool {i+1}: {defn}")
    
    # Test direct schema access
    tool_obj = registry.get("test_tool")
    if tool_obj:
        print(f"Direct tool schema: {tool_obj.get_schema()}")
    else:
        print("Tool not found in registry")

if __name__ == "__main__":
    main()