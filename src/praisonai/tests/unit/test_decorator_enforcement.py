#!/usr/bin/env python3
"""
Test decorator enforcement in non-agent contexts.
"""

import sys
import os

# Add the praisonai-agents module to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'praisonai-agents')))

def test_decorator_enforcement():
    """Test decorator enforcement."""
    print("🧪 Testing Decorator Enforcement")
    print("=" * 35)
    
    try:
        from praisonaiagents.approval import require_approval, set_approval_callback, ApprovalDecision
        
        # Set denial callback
        def auto_deny_callback(function_name, arguments, risk_level):
            return ApprovalDecision(approved=False, reason="Test denial")
        
        set_approval_callback(auto_deny_callback)
        
        @require_approval(risk_level="critical")
        def test_function(command: str) -> str:
            """A test function that requires approval."""
            return f"Executed: {command}"
        
        print("Attempting to execute command directly (should be blocked)...")
        
        try:
            result = test_function("dangerous command")
            print("❌ Command executed when it should have been denied!")
            assert False, "Command executed when it should have been denied!"
        except PermissionError:
            print("✅ Command correctly blocked by approval system")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            assert False, f"Unexpected error: {e}"
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        assert False, f"Test failed: {e}"

if __name__ == "__main__":
    test_decorator_enforcement()
    print("🎉 Decorator enforcement test completed!") 