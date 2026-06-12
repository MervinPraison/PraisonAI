#!/usr/bin/env python3
"""
Simple test to verify toolsets implementation works.
"""

import sys
import os

# Add the praisonai-agents package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

def test_basic_functionality():
    """Test basic toolsets functionality."""
    print("Testing basic toolsets functionality...")
    
    try:
        from praisonaiagents.toolsets import list_toolsets, resolve_toolset
        
        # Test listing toolsets
        toolsets = list_toolsets()
        print(f"✅ Available toolsets: {toolsets}")
        
        # Test resolving a toolset
        safe_tools = resolve_toolset("safe")
        print(f"✅ Safe toolset tools: {safe_tools}")
        
        research_tools = resolve_toolset("research")
        print(f"✅ Research toolset tools: {research_tools[:5]}...")  # Show first 5
        
        return True
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_integration():
    """Test agent integration with toolsets."""
    print("\nTesting Agent integration...")
    
    # Set up minimal environment
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    
    try:
        from praisonaiagents import Agent
        
        # Test creating agent with toolsets
        agent = Agent(
            name="test_agent",
            role="Test Agent",
            toolsets=["safe"]
        )
        print(f"✅ Agent created with {len(agent.tools)} tools")
        
        return True
    except Exception as e:
        print(f"❌ Agent integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_yaml_validation():
    """Test YAML validation for toolsets."""
    print("\nTesting YAML validation...")
    
    # Add praisonai to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai'))
    
    try:
        from praisonai.tool_resolver import validate_yaml_tools
        
        # Test valid config
        config = {
            "agents": {
                "test_agent": {
                    "role": "Test Agent",
                    "toolsets": ["safe"]
                }
            }
        }
        
        missing = validate_yaml_tools(config)
        print(f"✅ YAML validation working. Missing items: {missing}")
        
        return True
    except Exception as e:
        print(f"❌ YAML validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_error_handling():
    """Test error handling for invalid toolsets."""
    print("\nTesting error handling...")
    
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    
    try:
        from praisonaiagents import Agent
        
        # This should fail fast
        try:
            agent = Agent(
                name="fail_agent",
                role="Should Fail",
                toolsets=["nonexistent_toolset_xyz"]
            )
            print("❌ Expected agent creation to fail with invalid toolset")
            return False
        except (ValueError, KeyError, ImportError) as e:
            print(f"✅ Agent creation correctly failed with: {type(e).__name__}")
            return True
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("🛠️  Testing PraisonAI Named Toolsets Implementation")
    print("=" * 60)
    
    tests = [
        test_basic_functionality,
        test_agent_integration,
        test_yaml_validation,
        test_error_handling
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! Named toolsets implementation is working!")
        return 0
    else:
        print("❌ Some tests failed. Check output above.")
        return 1

if __name__ == "__main__":
    exit(main())