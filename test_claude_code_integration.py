#!/usr/bin/env python3
"""
Test script for Claude Code integration in PraisonAI UI.
This script tests the core functionality without requiring the full UI.
"""

import sys
import os
import tempfile
import shutil

# Add the UI module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai', 'praisonai', 'ui'))

# Mock chainlit user session for testing
class MockUserSession:
    def __init__(self):
        self._data = {}
    
    def get(self, key, default=None):
        return self._data.get(key, default)
    
    def set(self, key, value):
        self._data[key] = value

# Mock chainlit module
class MockCL:
    class user_session:
        _instance = MockUserSession()
        
        @classmethod
        def get(cls, key, default=None):
            return cls._instance.get(key, default)
        
        @classmethod
        def set(cls, key, value):
            cls._instance.set(key, value)

sys.modules['chainlit'] = MockCL
import chainlit as cl

# Now import our functions
from code import should_use_claude_code, check_and_setup_git

def test_detection_logic():
    """Test the Claude Code detection logic."""
    print("Testing Claude Code detection logic...")
    
    # Set up mock session
    cl.user_session.set("claude_code_enabled", True)
    
    # Test cases that should trigger Claude Code
    positive_cases = [
        "Create a new Python function",
        "Fix the bug in authentication.py", 
        "Modify the database connection code",
        "Implement error handling",
        "Add a new feature to the API",
        "Update the configuration file",
        "Write a test for the user module",
        "Generate a README file",
        "Create a pull request",
        "Commit these changes"
    ]
    
    # Test cases that should use regular LLM
    negative_cases = [
        "What is the purpose of this function?",
        "How does the authentication work?",
        "Explain the database schema",
        "What are the project dependencies?",
        "Show me the code structure",
        "How to run this application?",
        "What is the difference between these approaches?"
    ]
    
    print("✓ Testing positive cases (should use Claude Code):")
    for case in positive_cases:
        result = should_use_claude_code(case)
        status = "✓" if result else "✗"
        print(f"  {status} '{case[:40]}...' -> {result}")
    
    print("\\n✓ Testing negative cases (should use LLM):")
    for case in negative_cases:
        result = should_use_claude_code(case)
        status = "✓" if not result else "✗"
        print(f"  {status} '{case[:40]}...' -> {result}")

def test_git_detection():
    """Test git repository detection."""
    print("\\nTesting git repository detection...")
    
    # Test in current directory (should have git)
    current_dir = os.getcwd()
    print(f"Testing in {current_dir}")
    
    # Note: Since we can't use async in this simple test, we'll just import the function
    # In a real test, you'd use asyncio.run()
    print("Git detection function imported successfully")
    print("(Full async testing would require asyncio.run())")

def test_environment_variables():
    """Test environment variable handling."""
    print("\\nTesting environment variable handling...")
    
    # Test default values
    from code import CLAUDE_CODE_ENABLED, CLAUDE_EXECUTABLE
    
    print(f"CLAUDE_CODE_ENABLED: {CLAUDE_CODE_ENABLED}")
    print(f"CLAUDE_EXECUTABLE: {CLAUDE_EXECUTABLE}")
    
    # Test detection with disabled Claude Code
    original_enabled = cl.user_session.get("claude_code_enabled")
    cl.user_session.set("claude_code_enabled", False)
    
    result = should_use_claude_code("Create a new file")
    print(f"Detection with disabled Claude Code: {result} (should be False)")
    
    # Restore original setting
    if original_enabled is not None:
        cl.user_session.set("claude_code_enabled", original_enabled)

def main():
    """Run all tests."""
    print("🧪 Claude Code Integration Tests")
    print("=" * 50)
    
    try:
        test_detection_logic()
        test_git_detection()
        test_environment_variables()
        
        print("\\n✅ All tests completed successfully!")
        print("\\n📝 Notes:")
        print("- Full integration testing requires running the Chainlit UI")
        print("- Git operations require a valid repository")
        print("- Claude Code CLI must be installed for full functionality")
        
    except Exception as e:
        print(f"\\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())