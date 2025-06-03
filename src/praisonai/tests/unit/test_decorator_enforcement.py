#!/usr/bin/env python3
"""
Test script to verify that the require_approval decorator now enforces approval
even when tools are called directly (not through agent.execute_tool).
"""

import sys
import os

# Add the praisonai-agents module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_decorator_enforcement():
    """Test that the decorator actually enforces approval."""
    print("🧪 Testing Decorator Enforcement")
    print("=" * 35)
    
    try:
        from praisonaiagents.tools.shell_tools import ShellTools
        from praisonaiagents.approval import set_approval_callback, ApprovalDecision
        
        # Set auto-denial to test enforcement
        def auto_deny(function_name, arguments, risk_level):
            print(f"🚫 Denying {function_name} (risk: {risk_level})")
            return ApprovalDecision(approved=False, reason='Test denial')
        
        set_approval_callback(auto_deny)
        
        shell_tools = ShellTools()
        
        print("Attempting to execute command directly (should be blocked)...")
        
        try:
            # This should now be blocked by the decorator
            result = shell_tools.execute_command('echo "This should be denied"')
            print('❌ Command executed when it should have been denied!')
            return False
        except PermissionError as e:
            print(f'✅ Decorator enforcement working: {e}')
            return True
        except Exception as e:
            print(f'❌ Unexpected error: {e}')
            return False
            
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        return False

if __name__ == "__main__":
    success = test_decorator_enforcement()
    if success:
        print("\n🎉 Decorator enforcement is working correctly!")
    else:
        print("\n❌ Decorator enforcement test failed!")
    sys.exit(0 if success else 1) 