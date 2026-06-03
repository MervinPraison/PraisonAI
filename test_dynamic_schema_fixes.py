#!/usr/bin/env python3
"""Test script to validate dynamic schema override fixes."""

import sys
import os

# Add the package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "praisonai-agents"))

def test_shallow_copy_fix():
    """Test that the shallow copy bug is fixed."""
    from praisonaiagents.tools.base import BaseTool
    
    class TestTool(BaseTool):
        name = "test_tool"
        description = "Test tool"
        
        def __init__(self):
            super().__init__(dynamic_schema_overrides=self._override)
        
        def _override(self, base_schema):
            # Modify the schema - this should NOT affect the tool's stored parameters
            modified = base_schema.copy()  # Shallow copy like in the examples
            modified["function"]["parameters"]["properties"]["new_param"] = {"type": "string"}
            return modified
        
        def run(self, **kwargs):
            return "test"
    
    tool = TestTool()
    original_params = str(tool.parameters)
    
    # Get schema twice - second time should be the same as first
    schema1 = tool.get_schema()
    schema2 = tool.get_schema()
    
    # Check that tool's internal parameters weren't mutated
    assert str(tool.parameters) == original_params, "Tool parameters were mutated!"
    
    # Both schemas should be identical
    assert schema1 == schema2, "Schemas are different between calls!"
    
    print("✓ Shallow copy fix validated")

def test_registry_override():
    """Test that registry-level overrides now work for BaseTool instances."""
    from praisonaiagents.tools.base import BaseTool
    from praisonaiagents.tools.registry import ToolRegistry
    
    class TestTool(BaseTool):
        name = "test_tool"
        description = "Test tool"
        
        def __init__(self):
            super().__init__()
        
        def run(self, **kwargs):
            return "test"
    
    def registry_override(base_schema):
        modified = base_schema.copy()
        modified["function"]["description"] = "REGISTRY OVERRIDE: " + modified["function"]["description"]
        return modified
    
    # Create registry and register tool with override
    registry = ToolRegistry()
    tool = TestTool()
    registry.register(tool, dynamic_schema_overrides=registry_override)
    
    # Get schema via registry - should include override
    definitions = registry.get_tool_definitions()
    assert len(definitions) == 1
    assert "REGISTRY OVERRIDE:" in definitions[0]["function"]["description"]
    
    print("✓ Registry override fix validated")

def test_function_tool_copy_fix():
    """Test that FunctionTool deep copy fix works."""
    from praisonaiagents.tools.decorator import tool
    
    def schema_override(base_schema):
        # This should not mutate the original tool's parameters
        modified = base_schema.copy()  # Shallow copy
        modified["function"]["parameters"]["properties"]["extra"] = {"type": "string"}
        return modified
    
    @tool(dynamic_schema_overrides=schema_override)
    def test_func(param1: str) -> str:
        """Test function."""
        return param1
    
    original_params = str(test_func.parameters)
    
    # Get schema twice
    schema1 = test_func.get_schema()
    schema2 = test_func.get_schema()
    
    # Tool parameters should be unchanged
    assert str(test_func.parameters) == original_params, "Function tool parameters were mutated!"
    
    # Both schemas should be identical
    assert schema1 == schema2, "Schemas are different between calls!"
    
    print("✓ FunctionTool copy fix validated")

if __name__ == "__main__":
    print("Testing dynamic schema override fixes...")
    
    try:
        test_shallow_copy_fix()
        test_registry_override()
        test_function_tool_copy_fix()
        
        print("\n✅ All tests passed! Fixes are working correctly.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)