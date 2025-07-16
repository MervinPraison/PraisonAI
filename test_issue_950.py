#!/usr/bin/env python3
"""
Test for issue #950: Convert praisonaiagents to praisonai imports
The goal is to enable: from PraisonAI import Agent instead of from PraisonAIAgents import Agent
"""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_issue_950_goal():
    """Test the specific goal stated in issue #950"""
    print("Testing issue #950 goal: from PraisonAI import Agent")
    
    try:
        # This is what the issue wants to achieve
        # Note: In Python, package names are case-sensitive, so we import from 'praisonai'
        # but the user goal is conceptually "from PraisonAI import Agent"
        from praisonai import Agent
        print("✅ SUCCESS: `from praisonai import Agent` works!")
        
        # Verify the class is functional
        assert Agent is not None, "Agent class should be available"
        assert hasattr(Agent, '__name__'), "Agent should have __name__ attribute"
        assert Agent.__name__ == 'Agent', f"Expected 'Agent', got '{Agent.__name__}'"
        
        print(f"✅ Agent class is properly available: {Agent}")
        
        # Test that we can also import other common classes mentioned in the issue
        from praisonai import Task, PraisonAIAgents
        print("✅ SUCCESS: `from praisonai import Task, PraisonAIAgents` works!")
        
        assert Task is not None, "Task class should be available"
        assert PraisonAIAgents is not None, "PraisonAIAgents class should be available"
        
        print(f"✅ Task class: {Task}")
        print(f"✅ PraisonAIAgents class: {PraisonAIAgents}")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

def test_backward_compatibility():
    """Test that the old pattern still works"""
    print("\nTesting backward compatibility...")
    
    try:
        # The old pattern should still work
        from praisonaiagents import Agent
        print("✅ SUCCESS: `from praisonaiagents import Agent` still works!")
        
        assert Agent is not None, "Agent class should be available"
        print(f"✅ Agent class: {Agent}")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

def test_package_name_case_sensitivity():
    """Test to clarify the case sensitivity issue"""
    print("\nTesting package name case sensitivity...")
    
    # In Python, package names are case-sensitive
    # The actual package name is 'praisonai' (lowercase)
    # but the issue mentions 'PraisonAI' (capitalized)
    
    try:
        # This should work (lowercase)
        from praisonai import Agent as AgentLowercase
        print("✅ SUCCESS: `from praisonai import Agent` works (lowercase package name)")
        
        # Try with uppercase (this should fail in most cases unless there's a PraisonAI package)
        try:
            from PraisonAI import Agent as AgentUppercase
            print("✅ SUCCESS: `from PraisonAI import Agent` works (uppercase package name)")
            
            # If both work, they should be the same
            if AgentLowercase is AgentUppercase:
                print("✅ Both import patterns reference the same class")
            else:
                print("⚠️  WARNING: Different classes imported from different packages")
                
        except ImportError as e:
            print(f"ℹ️  INFO: Uppercase package name not available: {e}")
            print("   This is expected - Python packages are case-sensitive")
            print("   The working pattern is: from praisonai import Agent")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False

if __name__ == "__main__":
    print("Testing Issue #950: Convert praisonaiagents to praisonai imports")
    print("=" * 60)
    
    tests = [
        test_issue_950_goal,
        test_backward_compatibility,
        test_package_name_case_sensitivity,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    print(f"Test Results: {sum(results)}/{len(results)} tests passed")
    
    if all(results):
        print("\n🎉 SUCCESS: Issue #950 goal achieved!")
        print("✅ Users can now use: from praisonai import Agent")
        print("✅ Backward compatibility maintained: from praisonaiagents import Agent")
        print("\nNote: In Python, package names are case-sensitive.")
        print("The correct import is: from praisonai import Agent (lowercase)")
        sys.exit(0)
    else:
        print("\n❌ FAILED: Some tests failed")
        sys.exit(1)