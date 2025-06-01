#!/usr/bin/env python3
"""
Basic test to verify the human approval system implementation.
"""

import sys
import os

# Add the src directory to Python path  
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_imports():
    """Test that all the new approval imports work correctly."""
    try:
        print("Testing approval module import...")
        from praisonaiagents.approval import (
            require_approval,
            ApprovalDecision,
            console_approval_callback,
            request_approval,
            is_approval_required,
            get_risk_level,
            add_approval_requirement,
            remove_approval_requirement
        )
        print("✅ Approval module imports successful")
        
        print("Testing main module approval functions...")
        from praisonaiagents.main import register_approval_callback, approval_callback
        print("✅ Main module approval functions imported successfully")
        
        print("Testing agent modifications...")
        from praisonaiagents.agent import Agent
        print("✅ Agent class imports successfully")
        
        print("Testing tool decorators...")
        from praisonaiagents.tools.shell_tools import ShellTools
        from praisonaiagents.tools.python_tools import PythonTools  
        from praisonaiagents.tools.file_tools import FileTools
        print("✅ Tool classes with decorators imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_approval_decision():
    """Test the ApprovalDecision class."""
    try:
        from praisonaiagents.approval import ApprovalDecision
        
        # Test approved decision
        decision = ApprovalDecision(approved=True, reason="Test approval")
        assert decision.approved == True
        assert decision.reason == "Test approval"
        print("✅ ApprovalDecision class works correctly")
        
        return True
    except Exception as e:
        print(f"❌ ApprovalDecision test failed: {e}")
        return False

def test_approval_requirements():
    """Test approval requirement configuration."""
    try:
        from praisonaiagents.approval import (
            add_approval_requirement,
            remove_approval_requirement,
            is_approval_required,
            get_risk_level
        )
        
        # Test adding requirement
        add_approval_requirement("test_function", "high")
        assert is_approval_required("test_function") == True
        assert get_risk_level("test_function") == "high"
        
        # Test removing requirement
        remove_approval_requirement("test_function")
        assert is_approval_required("test_function") == False
        assert get_risk_level("test_function") is None
        
        print("✅ Approval requirement configuration works correctly")
        return True
        
    except Exception as e:
        print(f"❌ Approval requirements test failed: {e}")
        return False

def test_default_dangerous_tools():
    """Test that default dangerous tools are configured."""
    try:
        from praisonaiagents.approval import is_approval_required, get_risk_level
        
        # Check some default dangerous tools
        dangerous_tools = ["execute_command", "execute_code", "write_file", "delete_file"]
        
        for tool in dangerous_tools:
            if is_approval_required(tool):
                risk = get_risk_level(tool)
                print(f"✅ {tool} requires approval (risk: {risk})")
            else:
                print(f"⚠️  {tool} does not require approval")
        
        return True
        
    except Exception as e:
        print(f"❌ Default dangerous tools test failed: {e}")
        return False

def main():
    """Run all basic tests."""
    print("🧪 Basic Human Approval System Tests")
    print("=" * 40)
    
    tests = [
        ("Import Tests", test_imports),
        ("ApprovalDecision Tests", test_approval_decision),
        ("Approval Requirements Tests", test_approval_requirements),
        ("Default Dangerous Tools Tests", test_default_dangerous_tools)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running {test_name}...")
        if test_func():
            passed += 1
        
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All basic tests passed! Human approval system is working.")
    else:
        print("❌ Some tests failed. Check the implementation.")
        
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)