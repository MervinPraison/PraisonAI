#!/usr/bin/env python3
"""
Debug decorator execution.
"""

import sys
import os
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

# Import the registry module first to ensure it's loaded
from praisonaiagents.tools.registry import get_registry

print("Registry before tool creation:", get_registry())

# Create the global registry instance first
registry = get_registry()
print(f"Global registry instance: {registry}")

# Now import and use the tool decorator
from praisonaiagents.tools.decorator import tool

def test_schema_override(base_schema):
    """Test schema override function."""
    schema = base_schema.copy()
    schema["function"]["description"] = "MODIFIED: " + schema["function"]["description"]
    return schema

print("Creating tool...")

@tool(name="debug_tool", dynamic_schema_overrides=test_schema_override)
def debug_function(query: str) -> str:
    """Debug function."""
    return f"Result: {query}"

print("Tool created. Checking registry...")
print(f"Tools in registry: {registry.list_tools()}")

# Also check with get_registry() again
print(f"Tools via get_registry(): {get_registry().list_tools()}")