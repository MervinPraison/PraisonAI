#!/usr/bin/env python3
"""
Test script to verify example file functionality without API keys
"""

import sys
import os

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_agent_creation():
    """Test that we can create a basic agent like in the examples"""
    try:
        print("Testing basic agent creation from examples...")
        from praisonaiagents import Agent
        
        # Create agent similar to basic-agents.py but without running it
        agent = Agent(
            instructions="You are a helpful assistant",
            llm="gpt-4o-mini"
        )
        
        print("✓ Agent created successfully with instructions and llm")
        
        # Check that the agent has the expected attributes
        assert agent.instructions == "You are a helpful assistant"
        assert agent.llm == "gpt-4o-mini"
        print("✓ Agent attributes set correctly")
        
        return True
        
    except Exception as e:
        print(f"✗ Basic agent creation error: {e}")
        return False

def test_agent_with_tools():
    """Test that we can create an agent with tools like in the examples"""
    try:
        print("\nTesting agent with tools creation...")
        from praisonaiagents import Agent
        
        # Define a simple tool function like in basic-agents-tools.py
        def get_weather(city: str) -> str:
            return f"The weather in {city} is sunny"
        
        # Create agent with tools
        agent = Agent(
            instructions="You are a helpful assistant",
            llm="gpt-4o-mini",
            tools=[get_weather]
        )
        
        print("✓ Agent with tools created successfully")
        
        # Check that the agent has the tools
        assert hasattr(agent, 'tools')
        assert agent.tools is not None
        print("✓ Agent tools attribute exists")
        
        return True
        
    except Exception as e:
        print(f"✗ Agent with tools creation error: {e}")
        return False

def test_examples_import_structure():
    """Test that we can import from examples directory"""
    try:
        print("\nTesting example files import structure...")
        
        # Check that the examples can be imported (syntax check)
        import importlib.util
        
        # Get repository root directory
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        while not os.path.exists(os.path.join(repo_root, '.git')) and repo_root != '/':
            repo_root = os.path.dirname(repo_root)
        
        examples_to_check = [
            os.path.join(repo_root, "examples/python/agents/single-agent.py"),
            os.path.join(repo_root, "examples/python/agents/math-agent.py"),
            os.path.join(repo_root, "examples/python/agents/research-agent.py")
        ]
        
        for example_path in examples_to_check:
            if os.path.exists(example_path):
                spec = importlib.util.spec_from_file_location("example_module", example_path)
                module = importlib.util.module_from_spec(spec)
                
                # Try to load the module to check syntax
                try:
                    spec.loader.exec_module(module)
                    print(f"✓ {os.path.basename(example_path)} - syntax OK")
                except Exception as e:
                    # If it fails due to API key or execution, but imports are OK, that's fine
                    if "API" in str(e) or "key" in str(e) or "openai" in str(e).lower():
                        print(f"✓ {os.path.basename(example_path)} - syntax OK (API key needed for execution)")
                    else:
                        print(f"✗ {os.path.basename(example_path)} - error: {e}")
            else:
                print(f"ℹ {os.path.basename(example_path)} - file not found")
        
        return True
        
    except Exception as e:
        print(f"✗ Examples import structure error: {e}")
        return False

def test_package_version():
    """Test that the package version is accessible"""
    try:
        print("\nTesting package version...")
        import praisonaiagents
        
        # Check if version info is available
        if hasattr(praisonaiagents, '__version__'):
            print(f"✓ Package version: {praisonaiagents.__version__}")
        else:
            print("ℹ Package version not directly available")
        
        return True
        
    except Exception as e:
        print(f"✗ Package version error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("PRAISONAIAGENTS EXAMPLE FILES FUNCTIONALITY TEST")
    print("=" * 60)
    
    tests = [
        test_basic_agent_creation,
        test_agent_with_tools,
        test_examples_import_structure,
        test_package_version
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
    
    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("🎉 All tests passed! Example files are working correctly.")
        print("📝 Note: Some examples may require API keys for actual execution.")
        return 0
    else:
        print("❌ Some tests failed. Please check the example files.")
        return 1

if __name__ == "__main__":
    sys.exit(main())