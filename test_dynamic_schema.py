#!/usr/bin/env python3
"""
Test script for dynamic schema override mechanism.

This tests the implementation described in GitHub issue #1807.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.tools import tool
from praisonaiagents.tools.registry import get_registry, get_tool_definitions

# Example 1: Runtime configuration that affects schema
class RuntimeConfig:
    def __init__(self):
        self.max_concurrent = 3
        self.available_models = ["gpt-4", "gpt-3.5-turbo"]

runtime_config = RuntimeConfig()

def delegate_schema_override(base_schema):
    """Dynamic schema override for delegation tool."""
    schema = base_schema.copy()
    
    # Update the description to reflect current runtime limit
    schema["function"]["description"] = (
        f"Delegate tasks to sub-agents. "
        f"Current runtime limit: {runtime_config.max_concurrent} concurrent tasks."
    )
    
    # Update the max_concurrent parameter constraint
    if "max_concurrent" in schema["function"]["parameters"]["properties"]:
        schema["function"]["parameters"]["properties"]["max_concurrent"]["maximum"] = runtime_config.max_concurrent
        schema["function"]["parameters"]["properties"]["max_concurrent"]["description"] = (
            f"Maximum parallel sub-tasks (current runtime limit: {runtime_config.max_concurrent})"
        )
    
    return schema

def model_selection_schema_override(base_schema):
    """Dynamic schema override for model selection tool."""
    schema = base_schema.copy()
    
    # Update available models list in schema
    if "model" in schema["function"]["parameters"]["properties"]:
        schema["function"]["parameters"]["properties"]["model"]["enum"] = runtime_config.available_models
        schema["function"]["parameters"]["properties"]["model"]["description"] = (
            f"Model to use. Available models: {', '.join(runtime_config.available_models)}"
        )
    
    return schema

# Define tools with dynamic schema overrides
@tool(dynamic_schema_overrides=delegate_schema_override)
def delegate_task(task_description: str, max_concurrent: int = 1) -> str:
    """Delegate a task to sub-agents."""
    return f"Delegated: {task_description} (max concurrent: {max_concurrent})"

@tool(dynamic_schema_overrides=model_selection_schema_override)  
def select_model(query: str, model: str = "gpt-4") -> str:
    """Select and use a specific model."""
    return f"Using {model} for: {query}"

# Test the implementation
def test_dynamic_schema_override():
    """Test that dynamic schema overrides work correctly."""
    print("=== Testing Dynamic Schema Override Mechanism ===\n")
    
    # Test 1: Get initial schemas
    print("1. Initial tool schemas:")
    definitions = get_tool_definitions()
    
    delegate_def = None
    model_def = None
    
    for defn in definitions:
        if defn["function"]["name"] == "delegate_task":
            delegate_def = defn
        elif defn["function"]["name"] == "select_model":
            model_def = defn
    
    if delegate_def:
        print(f"   Delegate task description: {delegate_def['function']['description']}")
        max_concurrent_prop = delegate_def["function"]["parameters"]["properties"].get("max_concurrent", {})
        print(f"   Max concurrent limit: {max_concurrent_prop.get('maximum', 'not set')}")
    
    if model_def:
        print(f"   Model selection description: {model_def['function']['description']}")
        model_prop = model_def["function"]["parameters"]["properties"].get("model", {})
        print(f"   Available models: {model_prop.get('enum', 'not set')}")
    
    print()
    
    # Test 2: Change runtime configuration
    print("2. Changing runtime configuration...")
    runtime_config.max_concurrent = 5
    runtime_config.available_models = ["gpt-4", "claude-3", "gemini-pro"]
    print(f"   New max_concurrent: {runtime_config.max_concurrent}")
    print(f"   New available_models: {runtime_config.available_models}")
    print()
    
    # Test 3: Get updated schemas (should reflect new configuration)
    print("3. Updated tool schemas:")
    definitions = get_tool_definitions()
    
    delegate_def = None
    model_def = None
    
    for defn in definitions:
        if defn["function"]["name"] == "delegate_task":
            delegate_def = defn
        elif defn["function"]["name"] == "select_model":
            model_def = defn
    
    if delegate_def:
        print(f"   Delegate task description: {delegate_def['function']['description']}")
        max_concurrent_prop = delegate_def["function"]["parameters"]["properties"].get("max_concurrent", {})
        print(f"   Max concurrent limit: {max_concurrent_prop.get('maximum', 'not set')}")
    
    if model_def:
        print(f"   Model selection description: {model_def['function']['description']}")
        model_prop = model_def["function"]["parameters"]["properties"].get("model", {})
        print(f"   Available models: {model_prop.get('enum', 'not set')}")
    
    print()
    
    # Test 4: Verify tools still work
    print("4. Testing tool execution:")
    result1 = delegate_task("Process data", max_concurrent=3)
    result2 = select_model("Summarize text", model="claude-3")
    
    print(f"   Delegate result: {result1}")
    print(f"   Model selection result: {result2}")
    
    print("\n=== Test Complete ===")

if __name__ == "__main__":
    test_dynamic_schema_override()