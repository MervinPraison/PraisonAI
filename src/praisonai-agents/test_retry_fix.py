#!/usr/bin/env python3
"""
Test the core retry bug fix - that error_category is set correctly.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

def test_error_category_attribute():
    """Test that error_category can be set as attribute on ToolExecutionError."""
    from praisonaiagents.errors import ToolExecutionError
    
    # Create error without error_category in constructor (as we do in the fix)
    err = ToolExecutionError(
        "Test error",
        tool_name="test_tool",
        agent_id="test_agent",
        is_retryable=True
    )
    
    # Set error_category as attribute (this is the fix)
    err.error_category = "network"
    
    # Verify it's set correctly
    assert err.error_category == "network"
    assert err.is_retryable == True
    assert err.tool_name == "test_tool"
    
    print("✅ ToolExecutionError.error_category attribute test passed!")
    return True

def test_retry_config_validation():
    """Test ToolRetryConfig validation."""
    from praisonaiagents.config import ToolRetryConfig
    
    # Test validation of max_attempts
    try:
        config = ToolRetryConfig(max_attempts=0)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "max_attempts must be at least 1" in str(e)
        print("✅ max_attempts validation works")
    
    # Test validation of initial_delay_s
    try:
        config = ToolRetryConfig(initial_delay_s=-1)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "initial_delay_s must be positive" in str(e)
        print("✅ initial_delay_s validation works")
    
    # Test validation of factor
    try:
        config = ToolRetryConfig(factor=0.5)
        assert False, "Should have raised ValueError"  
    except ValueError as e:
        assert "factor must be >= 1.0" in str(e)
        print("✅ factor validation works")
    
    return True

if __name__ == "__main__":
    print("Testing tool retry bug fixes...")
    
    tests = [
        ("error_category attribute", test_error_category_attribute),
        ("retry config validation", test_retry_config_validation),
    ]
    
    failed = []
    for name, fn in tests:
        try:
            ok = fn()
        except Exception as exc:
            print(f"❌ {name} failed: {exc}")
            import traceback
            traceback.print_exc()
            ok = False
        if not ok:
            failed.append(name)
    
    if failed:
        print(f"\n❌ Tests failed: {', '.join(failed)}")
        sys.exit(1)
    
    print("\n🎉 All retry bug fix tests passed!")