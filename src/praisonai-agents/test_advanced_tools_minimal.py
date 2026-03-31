#!/usr/bin/env python3
"""
Minimal test script for advanced tools functionality.
Tests the key issues identified in the original PR reviews.
"""

import sys
import os
import time

# Add the package to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_imports():
    """Test that advanced tools can be imported successfully."""
    try:
        from praisonaiagents.tools import (
            advanced_tool, cache, external, user_input,
            Priority, ToolContext, Hook, CacheConfig, ExternalConfig,
            Field, InputGroup, Choice, Range, Pattern,
            set_global_hooks, clear_global_hooks, register_external_handler,
            invalidate_cache, clear_all_caches, get_cache_stats
        )
        print("✅ All advanced tools imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False


def test_bare_decorator_usage():
    """Test that @advanced_tool works without parentheses (fixes original issue)."""
    try:
        from praisonaiagents.tools import advanced_tool

        @advanced_tool
        def simple_tool(x: int) -> int:
            return x * 2

        result = simple_tool(5)
        assert result == 10, f"Expected 10, got {result}"
        print("✅ Bare @tool decorator usage works")
        return True
    except Exception as e:
        print(f"❌ Bare decorator error: {e}")
        return False


def test_tool_with_parentheses():
    """Test that @advanced_tool() works with parentheses."""
    try:
        from praisonaiagents.tools import advanced_tool

        @advanced_tool()
        def parentheses_tool(x: int) -> int:
            return x * 3

        result = parentheses_tool(4)
        assert result == 12, f"Expected 12, got {result}"
        print("✅ @tool() decorator usage works")
        return True
    except Exception as e:
        print(f"❌ Parentheses decorator error: {e}")
        return False


def test_caching():
    """Test basic caching functionality."""
    try:
        from praisonaiagents.tools import advanced_tool, CacheConfig, get_cache_stats

        call_count = 0

        @advanced_tool(cache=CacheConfig(enabled=True, ttl=60))
        def cached_tool(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 10

        # First call
        result1 = cached_tool(3)
        assert result1 == 30, f"Expected 30, got {result1}"
        assert call_count == 1, f"Expected 1 call, got {call_count}"

        # Second call should use cache
        result2 = cached_tool(3)
        assert result2 == 30, f"Expected 30, got {result2}"
        assert call_count == 1, f"Expected 1 call (cached), got {call_count}"

        stats = get_cache_stats()
        assert stats['total_entries'] > 0, "Cache should have entries"

        print("✅ Basic caching functionality works")
        return True
    except Exception as e:
        print(f"❌ Caching error: {e}")
        return False


def test_external_execution():
    """Test external execution with proper handler registration."""
    try:
        from praisonaiagents.tools import advanced_tool, ExternalConfig, register_external_handler

        # Register a synchronous external handler
        def test_handler(func, context, external_config):
            return f"External: {func(*context.args, **context.kwargs)}"

        register_external_handler("test_executor", test_handler)

        @advanced_tool(external=ExternalConfig(executor="test_executor"))
        def external_tool(msg: str) -> str:
            return f"Original: {msg}"

        result = external_tool("hello")
        assert result == "External: Original: hello", f"Unexpected result: {result}"
        print("✅ External execution works with sync handler")
        return True
    except Exception as e:
        print(f"❌ External execution error: {e}")
        return False


def test_hooks():
    """Test global hooks functionality."""
    try:
        from praisonaiagents.tools import advanced_tool, Hook, Priority, set_global_hooks

        hook_calls = []

        def before_hook(context):
            hook_calls.append(f"before:{context.tool_name}")

        def after_hook(context):
            hook_calls.append(f"after:{context.tool_name}")

        # Set global hooks
        set_global_hooks(
            before=[Hook(handler=before_hook, priority=Priority.NORMAL)],
            after=[Hook(handler=after_hook, priority=Priority.NORMAL)]
        )

        @advanced_tool
        def hooked_tool(x: int) -> int:
            return x + 1

        result = hooked_tool(5)
        assert result == 6, f"Expected 6, got {result}"
        assert "before:hooked_tool" in hook_calls, f"Before hook not called: {hook_calls}"
        assert "after:hooked_tool" in hook_calls, f"After hook not called: {hook_calls}"

        print("✅ Global hooks functionality works")
        return True
    except Exception as e:
        print(f"❌ Hooks error: {e}")
        return False


def test_input_validation_classes():
    """Test that input validation classes work correctly."""
    try:
        from praisonaiagents.tools import Field, InputGroup, Choice, Range, Pattern

        # Test Field
        field = Field(name="test_field", description="Test field", required=True)
        assert field.name == "test_field"

        # Test InputGroup
        group = InputGroup(name="test_group", fields=[field])
        assert len(group.fields) == 1

        # Test Choice
        choice = Choice(options=["option1", "option2"])
        assert len(choice.options) == 2

        # Test Range with correct parameter names (fixes original issue)
        range_obj = Range(min_val=0, max_val=100)
        assert range_obj.min_val == 0
        assert range_obj.max_val == 100

        # Test Pattern
        pattern = Pattern(regex=r"^\d+$")
        assert pattern.regex == r"^\d+$"

        print("✅ Input validation classes work correctly")
        return True
    except Exception as e:
        print(f"❌ Input validation error: {e}")
        return False


def test_thread_safety():
    """Basic thread safety test (checking locks exist)."""
    try:
        from praisonaiagents.tools.advanced import _lock
        
        # Check that the lock object exists and is a RLock
        assert hasattr(_lock, '__enter__'), "Lock should support context manager"
        
        # Test basic lock acquisition
        with _lock:
            pass
            
        print("✅ Thread safety mechanisms in place")
        return True
    except Exception as e:
        print(f"❌ Thread safety error: {e}")
        return False


def run_all_tests():
    """Run all tests and report results."""
    tests = [
        test_imports,
        test_bare_decorator_usage,
        test_tool_with_parentheses,
        test_caching,
        test_external_execution,
        test_hooks,
        test_input_validation_classes,
        test_thread_safety
    ]
    
    passed = 0
    total = len(tests)
    
    print(f"Running {total} tests...\n")
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ {test.__name__} failed with unexpected error: {e}")
        print()
    
    print(f"\nResults: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Advanced tools implementation is working correctly.")
        return True
    else:
        print("⚠️  Some tests failed. Please review the implementation.")
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)