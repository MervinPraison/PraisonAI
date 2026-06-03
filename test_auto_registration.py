#!/usr/bin/env python3
"""
Test automatic registration in @tool decorator.
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
    schema = base_schema.copy()
    schema["function"]["description"] = "MODIFIED: " + schema["function"]["description"]
    return schema

print("Creating tool with @tool decorator...")

@tool(name="auto_registered_tool", dynamic_schema_overrides=test_schema_override)
def test_function(query: str) -> str:
    """Test function for auto registration."""
    return f"Result: {query}"

print("Tool created. Checking registry...")
registry = get_registry()
print(f"Tools in registry: {registry.list_tools()}")

if "auto_registered_tool" in registry.list_tools():
    print("SUCCESS: Tool was automatically registered!")
    definitions = get_tool_definitions()
    for defn in definitions:
        if defn["function"]["name"] == "auto_registered_tool":
            print(f"Schema: {defn}")
else:
    print("FAILED: Tool was not automatically registered")