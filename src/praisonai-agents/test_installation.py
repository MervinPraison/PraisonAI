#!/usr/bin/env python3
"""
Test script to verify praisonaiagents installation
"""

import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_import():
    """Test that we can import the basic components"""
    try:
        print("Testing basic imports...")
        from praisonaiagents import Agent
        print("✓ Agent imported successfully")
        
        from praisonaiagents import Task
        print("✓ Task imported successfully")
        
        from praisonaiagents import Tools
        print("✓ Tools imported successfully")
        
        from praisonaiagents import PraisonAIAgents
        print("✓ PraisonAIAgents imported successfully")
        
        print("\nAll basic imports successful!")
        return True
        
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False

def test_agent_creation():
    """Test that we can create an Agent instance"""
    try:
        print("\nTesting Agent creation...")
        from praisonaiagents import Agent
        
        # Create a simple agent without LLM to avoid API key requirements
        agent = Agent(
            instructions="You are a helpful assistant",
            llm=None  # No LLM to avoid API key requirements
        )
        print("✓ Agent created successfully")
        
        # Test that the agent has expected attributes
        assert hasattr(agent, 'instructions')
        assert hasattr(agent, 'llm')
        print("✓ Agent has expected attributes")
        
        return True
        
    except Exception as e:
        print(f"✗ Agent creation error: {e}")
        return False

def test_tools_creation():
    """Test that we can create tools"""
    try:
        print("\nTesting Tools creation...")
        from praisonaiagents import Tools
        
        # Create a simple tool function
        def sample_tool(input_text: str) -> str:
            return f"Processed: {input_text}"
        
        tools = Tools()
        print("✓ Tools instance created successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Tools creation error: {e}")
        return False

def test_package_structure():
    """Test that the package structure is correct"""
    try:
        print("\nTesting package structure...")
        import praisonaiagents
        
        # Check that the package has the expected attributes
        expected_attrs = ['Agent', 'Task', 'Tools', 'PraisonAIAgents']
        
        for attr in expected_attrs:
            if hasattr(praisonaiagents, attr):
                print(f"✓ {attr} found in package")
            else:
                print(f"✗ {attr} not found in package")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ Package structure error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("PRAISONAIAGENTS INSTALLATION TEST")
    print("=" * 50)
    
    tests = [
        test_basic_import,
        test_agent_creation,
        test_tools_creation,
        test_package_structure
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 50)
    
    if failed == 0:
        print("🎉 All tests passed! Installation is successful.")
        return 0
    else:
        print("❌ Some tests failed. Please check the installation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())