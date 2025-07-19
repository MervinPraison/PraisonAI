#!/usr/bin/env python3
"""
Test script for advanced tools functionality.
This script validates that the new advanced tools features work correctly.
"""

import sys
import os

# Add the package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_imports():
    """Test that all advanced tools components can be imported."""
    try:
        from praisonaiagents.tools import (
            tool, cache, external, user_input,
            Field, InputGroup, Choice, Range, Pattern,
            ToolContext, Hook, CacheConfig, ExternalConfig, Priority,
            set_global_hooks, clear_global_hooks, register_external_handler,
            invalidate_cache, clear_all_caches, get_cache_stats
        )
        print("✅ All advanced tools imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False

def test_basic_tool_decorator():
    """Test basic @tool decorator functionality."""
    try:
        from praisonaiagents.tools import tool
        
        @tool
        def simple_tool(x: int) -> int:
            """A simple test tool."""
            return x * 2
        
        # Test that the tool works
        result = simple_tool(5)
        assert result == 10, f"Expected 10, got {result}"
        
        # Test that metadata is attached
        assert hasattr(simple_tool, '_tool_metadata'), "Tool metadata not attached"
        metadata = simple_tool._tool_metadata
        assert metadata['name'] == 'simple_tool', f"Wrong tool name: {metadata['name']}"
        
        print("✅ Basic @tool decorator works")
        return True
    except Exception as e:
        print(f"❌ Basic tool decorator error: {e}")
        return False

def test_hooks():
    """Test pre/post execution hooks."""
    try:
        from praisonaiagents.tools import tool, ToolContext
        
        # Track hook execution
        hook_calls = []
        
        def before_hook(context: ToolContext):
            hook_calls.append(f"before_{context.tool_name}")
        
        def after_hook(context: ToolContext):
            hook_calls.append(f"after_{context.tool_name}")
        
        @tool(before=before_hook, after=after_hook)
        def hooked_tool(x: int) -> int:
            """Tool with hooks."""
            return x + 1
        
        # Execute the tool
        result = hooked_tool(5)
        assert result == 6, f"Expected 6, got {result}"
        
        # Check that hooks were called
        assert "before_hooked_tool" in hook_calls, "Before hook not called"
        assert "after_hooked_tool" in hook_calls, "After hook not called"
        
        print("✅ Hooks functionality works")
        return True
    except Exception as e:
        print(f"❌ Hooks error: {e}")
        return False

def test_caching():
    """Test caching functionality."""
    try:
        from praisonaiagents.tools import tool, cache
        import time
        
        call_count = 0
        
        @tool
        @cache(ttl=60)  # 1 minute cache
        def cached_tool(x: int) -> dict:
            """Tool with caching."""
            nonlocal call_count
            call_count += 1
            return {"value": x * 2, "call_count": call_count}
        
        # First call
        result1 = cached_tool(5)
        assert result1["value"] == 10, f"Expected 10, got {result1['value']}"
        assert call_count == 1, f"Expected 1 call, got {call_count}"
        
        # Second call should be cached
        result2 = cached_tool(5)
        assert result2["value"] == 10, f"Expected 10, got {result2['value']}"
        assert call_count == 1, f"Expected 1 call (cached), got {call_count}"
        
        print("✅ Caching functionality works")
        return True
    except Exception as e:
        print(f"❌ Caching error: {e}")
        return False

def test_external_markers():
    """Test external execution markers."""
    try:
        from praisonaiagents.tools import tool, external
        
        @tool
        @external
        def external_tool(x: int) -> int:
            """Tool marked for external execution."""
            return x * 3
        
        # For now, external tools execute normally
        result = external_tool(4)
        assert result == 12, f"Expected 12, got {result}"
        
        # Check metadata
        metadata = external_tool._tool_metadata
        assert metadata['external_config'] is not None, "External config not set"
        
        print("✅ External execution markers work")
        return True
    except Exception as e:
        print(f"❌ External markers error: {e}")
        return False

def test_user_input_fields():
    """Test structured user input fields."""
    try:
        from praisonaiagents.tools import tool, user_input, Field, Choice
        
        @tool
        @user_input(
            Field(name="name", type=str, description="User name"),
            Field(name="priority", type=Choice(["low", "high"]), default="low")
        )
        def input_tool(name: str, priority: str = "low") -> dict:
            """Tool with structured input."""
            return {"name": name, "priority": priority}
        
        result = input_tool("test", "high")
        assert result["name"] == "test", f"Expected 'test', got {result['name']}"
        assert result["priority"] == "high", f"Expected 'high', got {result['priority']}"
        
        # Check metadata
        metadata = input_tool._tool_metadata
        assert metadata['inputs'] is not None, "Inputs not set"
        assert len(metadata['inputs']) == 2, f"Expected 2 inputs, got {len(metadata['inputs'])}"
        
        print("✅ User input fields work")
        return True
    except Exception as e:
        print(f"❌ User input fields error: {e}")
        return False

def test_backward_compatibility():
    """Test that existing tools still work."""
    try:
        # Test that we can still import existing tools
        from praisonaiagents.tools import TOOL_MAPPINGS
        
        # Check that tool mappings still exist
        assert len(TOOL_MAPPINGS) > 0, "Tool mappings empty"
        assert 'internet_search' in TOOL_MAPPINGS, "internet_search tool missing"
        
        print("✅ Backward compatibility maintained")
        return True
    except Exception as e:
        print(f"❌ Backward compatibility error: {e}")
        return False

def test_comprehensive_example():
    """Test a comprehensive tool with multiple features."""
    try:
        from praisonaiagents.tools import tool, cache, Field, Choice, ToolContext, Priority
        
        hook_calls = []
        
        def validator(context: ToolContext):
            hook_calls.append("validator")
        
        def logger(context: ToolContext):
            hook_calls.append("logger")
        
        @tool(
            name="comprehensive_test",
            description="A comprehensive test tool",
            before=[(validator, Priority.HIGHEST), (logger, Priority.MEDIUM)],
            cache={"ttl": 300, "tags": ["test"]},
            inputs=[
                Field(name="data", type=str),
                Field(name="format", type=Choice(["json", "xml"]), default="json")
            ]
        )
        def comprehensive_tool(data: str, format: str = "json") -> dict:
            """Comprehensive test tool."""
            return {"data": data, "format": format, "processed": True}
        
        result = comprehensive_tool("test_data", "xml")
        assert result["data"] == "test_data", "Data not preserved"
        assert result["format"] == "xml", "Format not preserved"
        assert result["processed"] is True, "Processed flag not set"
        
        # Check hooks were called
        assert "validator" in hook_calls, "Validator hook not called"
        assert "logger" in hook_calls, "Logger hook not called"
        
        print("✅ Comprehensive example works")
        return True
    except Exception as e:
        print(f"❌ Comprehensive example error: {e}")
        return False

def run_all_tests():
    """Run all tests and report results."""
    print("🧪 Testing Advanced Tools Implementation")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_backward_compatibility,
        test_basic_tool_decorator,
        test_hooks,
        test_caching,
        test_external_markers,
        test_user_input_fields,
        test_comprehensive_example
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("🎉 All tests passed! Advanced tools implementation is working correctly.")
        return True
    else:
        print(f"⚠️  {total - passed} tests failed. Implementation needs review.")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)