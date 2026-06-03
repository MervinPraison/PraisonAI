#!/usr/bin/env python3
"""
Debug script to trace schema method calls.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.tools import tool
from praisonaiagents.tools.registry import get_registry, get_tool_definitions

def test_schema_override(base_schema):
    """Test schema override function."""
    print(f"Override called in override function with: {base_schema['function']['description']}")
    schema = base_schema.copy()
    schema["function"]["description"] = "MODIFIED: " + schema["function"]["description"]
    return schema

print("Creating tool...")
test_tool = tool(name="test_tool", dynamic_schema_overrides=test_schema_override)(
    lambda query: f"Result: {query}"
)

def main():
    print("=== Test Schema Method Calls ===")
    
    # Test direct schema access
    print("1. Calling tool.get_schema() directly:")
    direct_schema = test_tool.get_schema()
    print(f"Direct schema: {direct_schema['function']['description']}")
    
    # Test registry registration
    print("\n2. Registering with registry:")
    registry = get_registry()
    registry.register(test_tool)
    
    # Test get_tool_definitions
    print("\n3. Getting tool definitions from registry:")
    definitions = get_tool_definitions()
    if definitions:
        print(f"Registry schema: {definitions[0]['function']['description']}")
    
    # Test getting the tool from registry
    print("\n4. Getting tool from registry and calling its get_schema():")
    registered_tool = registry.get("test_tool")
    if registered_tool:
        registry_tool_schema = registered_tool.get_schema()
        print(f"Registered tool schema: {registry_tool_schema['function']['description']}")

if __name__ == "__main__":
    main()