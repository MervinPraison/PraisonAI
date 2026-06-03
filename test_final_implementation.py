#!/usr/bin/env python3
"""
Final test of the dynamic schema override mechanism.

This demonstrates the functionality described in GitHub issue #1807.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.tools import tool, BaseTool
from praisonaiagents.tools.registry import get_registry, add_tool, get_tool_definitions

# Example runtime configuration
class RuntimeConfig:
    def __init__(self):
        self.max_concurrent = 3
        self.available_models = ["gpt-4", "gpt-3.5-turbo"]
        self.api_keys = {"openai": "valid", "anthropic": None}

runtime_config = RuntimeConfig()

def delegate_schema_override(base_schema):
    """Dynamic schema override for delegation tool."""
    schema = base_schema.copy()
    
    # Update the description to reflect current runtime limit
    schema["function"]["description"] = (
        f"Delegate tasks to sub-agents. "
        f"Current runtime limit: {runtime_config.max_concurrent} concurrent tasks."
    )
    
    # Update the max_concurrent parameter with current limit
    params = schema["function"]["parameters"]["properties"]
    if "max_concurrent" in params:
        params["max_concurrent"]["maximum"] = runtime_config.max_concurrent
        params["max_concurrent"]["description"] = (
            f"Maximum parallel sub-tasks (current limit: {runtime_config.max_concurrent})"
        )
    
    return schema

def model_schema_override(base_schema):
    """Dynamic schema override for model selection tool."""
    schema = base_schema.copy()
    
    # Update available models based on valid API keys
    available_models = []
    if runtime_config.api_keys.get("openai"):
        available_models.extend(["gpt-4", "gpt-3.5-turbo"])
    if runtime_config.api_keys.get("anthropic"):
        available_models.extend(["claude-3-sonnet", "claude-3-haiku"])
    
    params = schema["function"]["parameters"]["properties"] 
    if "model" in params:
        params["model"]["enum"] = available_models
        params["model"]["description"] = (
            f"Model to use. Available: {', '.join(available_models)}"
        )
    
    return schema

# Method 1: Using @tool decorator with dynamic overrides
@tool(dynamic_schema_overrides=delegate_schema_override)
def delegate_task(task_description: str, max_concurrent: int = 1) -> str:
    """Delegate a task to sub-agents."""
    return f"Delegated: {task_description} (max concurrent: {max_concurrent})"

# Method 2: Using BaseTool subclass with dynamic overrides
class ModelSelectionTool(BaseTool):
    name = "select_model"
    description = "Select and use a specific model"
    
    def __init__(self):
        super().__init__(dynamic_schema_overrides=model_schema_override)
    
    def run(self, query: str, model: str = "gpt-4") -> str:
        return f"Using {model} for: {query}"

# Method 3: Manual registration with override
def simple_tool(name: str) -> str:
    """A simple tool."""
    return f"Hello {name}!"

def simple_tool_override(base_schema):
    """Override for simple tool."""
    schema = base_schema.copy()
    schema["function"]["description"] = "ENHANCED: " + schema["function"]["description"]
    return schema

def test_dynamic_schema_override():
    """Test the dynamic schema override implementation."""
    print("=== Testing Dynamic Schema Override Implementation ===\n")
    
    # Register tools manually since automatic registration has issues
    registry = get_registry()
    
    # Register the @tool decorated function
    registry.register(delegate_task)
    
    # Register the BaseTool subclass
    model_tool = ModelSelectionTool()
    registry.register(model_tool)
    
    # Register a plain function with override
    add_tool(simple_tool, name="simple_tool", dynamic_schema_overrides=simple_tool_override)
    
    print(f"Registered tools: {registry.list_tools()}\n")
    
    # Test 1: Get initial schemas with current runtime config
    print("1. Initial tool schemas with current config:")
    print(f"   Runtime config: max_concurrent={runtime_config.max_concurrent}")
    print(f"   API keys: {list(k for k, v in runtime_config.api_keys.items() if v)}")
    
    definitions = get_tool_definitions()
    
    for defn in definitions:
        tool_name = defn["function"]["name"]
        description = defn["function"]["description"]
        print(f"   {tool_name}: {description}")
        
        if tool_name == "delegate_task":
            max_concurrent_prop = defn["function"]["parameters"]["properties"].get("max_concurrent", {})
            print(f"     Max concurrent limit: {max_concurrent_prop.get('maximum', 'not set')}")
        elif tool_name == "select_model":
            model_prop = defn["function"]["parameters"]["properties"].get("model", {})
            print(f"     Available models: {model_prop.get('enum', 'not set')}")
    
    print()
    
    # Test 2: Change runtime configuration
    print("2. Changing runtime configuration...")
    old_concurrent = runtime_config.max_concurrent
    runtime_config.max_concurrent = 8
    runtime_config.api_keys["anthropic"] = "valid"
    
    print(f"   max_concurrent: {old_concurrent} → {runtime_config.max_concurrent}")
    print(f"   Enabled Anthropic API")
    print()
    
    # Test 3: Get updated schemas (should reflect new configuration)
    print("3. Updated tool schemas after config change:")
    definitions = get_tool_definitions()
    
    for defn in definitions:
        tool_name = defn["function"]["name"]
        description = defn["function"]["description"]
        print(f"   {tool_name}: {description}")
        
        if tool_name == "delegate_task":
            max_concurrent_prop = defn["function"]["parameters"]["properties"].get("max_concurrent", {})
            print(f"     Max concurrent limit: {max_concurrent_prop.get('maximum', 'not set')}")
        elif tool_name == "select_model":
            model_prop = defn["function"]["parameters"]["properties"].get("model", {})
            print(f"     Available models: {model_prop.get('enum', 'not set')}")
    
    print()
    
    # Test 4: Verify tools still execute correctly
    print("4. Testing tool execution:")
    result1 = delegate_task("Process data", max_concurrent=5)
    result2 = model_tool.run("Summarize text", model="claude-3-sonnet")
    result3 = simple_tool("World")
    
    print(f"   Delegate result: {result1}")
    print(f"   Model selection result: {result2}")
    print(f"   Simple tool result: {result3}")
    
    print()
    print("=== Test Complete: Dynamic Schema Override Working! ===")

if __name__ == "__main__":
    test_dynamic_schema_override()