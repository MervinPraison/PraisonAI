#!/usr/bin/env python3
"""
Debug script for tool registration.
"""

import sys
import os
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.tools import tool
from praisonaiagents.tools.registry import get_registry, get_tool_definitions

def test_schema_override(base_schema):
    """Test schema override function."""
    print(f"Override called with base schema: {base_schema}")
    schema = base_schema.copy()
    schema["function"]["description"] = "MODIFIED: " + schema["function"]["description"]
    return schema

print("Creating tool...")
test_tool = tool(name="test_tool", dynamic_schema_overrides=test_schema_override)(
    lambda query: f"Result: {query}"
)

print(f"Tool created: {test_tool}")
print(f"Tool name: {test_tool.name}")

def main():
    print("=== Debug Tool Registration ===")
    
    # Get registry and check what's registered
    registry = get_registry()
    print(f"Registry: {registry}")
    print(f"Tools in registry: {registry.list_tools()}")
    
    # Try manual registration
    print("Manually registering tool...")
    registry.register(test_tool)
    print(f"Tools after manual registration: {registry.list_tools()}")
    
    # Get tool definitions
    definitions = get_tool_definitions()
    print(f"Number of tool definitions: {len(definitions)}")
    
    for i, defn in enumerate(definitions):
        print(f"Tool {i+1}: {defn}")

if __name__ == "__main__":
    main()