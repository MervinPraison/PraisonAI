#!/usr/bin/env python3
"""
Test script to verify the new import pattern works correctly.
This tests both the new import pattern and backward compatibility.
"""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_new_import_pattern():
    """Test the new import pattern: from PraisonAI import Agent"""
    print("Testing new import pattern...")
    
    try:
        # Test importing from PraisonAI (note: this is actually importing from praisonai package)
        from praisonai import Agent, Task, PraisonAIAgents
        print("✓ Successfully imported Agent, Task, PraisonAIAgents from praisonai")
        
        # Test that the classes are available
        assert Agent is not None, "Agent class should be available"
        assert Task is not None, "Task class should be available"
        assert PraisonAIAgents is not None, "PraisonAIAgents class should be available"
        
        print("✓ All classes are properly available")
        
        # Test that we can access the class names
        print(f"✓ Agent class: {Agent.__name__}")
        print(f"✓ Task class: {Task.__name__}")
        print(f"✓ PraisonAIAgents class: {PraisonAIAgents.__name__}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error testing new import pattern: {e}")
        return False

def test_backward_compatibility():
    """Test backward compatibility: from praisonaiagents import Agent"""
    print("\nTesting backward compatibility...")
    
    try:
        # Test the old import pattern still works
        from praisonaiagents import Agent, Task, PraisonAIAgents
        print("✓ Successfully imported Agent, Task, PraisonAIAgents from praisonaiagents")
        
        # Test that the classes are available
        assert Agent is not None, "Agent class should be available"
        assert Task is not None, "Task class should be available"
        assert PraisonAIAgents is not None, "PraisonAIAgents class should be available"
        
        print("✓ All classes are properly available")
        
        return True
        
    except Exception as e:
        print(f"✗ Error testing backward compatibility: {e}")
        return False

def test_class_identity():
    """Test that both import patterns reference the same classes"""
    print("\nTesting class identity...")
    
    try:
        # Import from both packages
        from praisonai import Agent as PraisonAIAgent, Task as PraisonAITask
        from praisonaiagents import Agent as PraisonAIAgentsAgent, Task as PraisonAIAgentsTask
        
        # They should be the same class
        assert PraisonAIAgent is PraisonAIAgentsAgent, "Agent classes should be identical"
        assert PraisonAITask is PraisonAIAgentsTask, "Task classes should be identical"
        
        print("✓ Both import patterns reference the same classes")
        
        return True
        
    except Exception as e:
        print(f"✗ Error testing class identity: {e}")
        return False

def test_no_conflicts():
    """Test that there are no conflicts with existing PraisonAI class"""
    print("\nTesting no conflicts...")
    
    try:
        # Import both the original PraisonAI and the new classes
        from praisonai import PraisonAI, Agent, Task
        
        # They should be different classes
        assert PraisonAI is not Agent, "PraisonAI should be different from Agent"
        assert PraisonAI is not Task, "PraisonAI should be different from Task"
        
        print("✓ No conflicts between PraisonAI and imported classes")
        
        return True
        
    except Exception as e:
        print(f"✗ Error testing conflicts: {e}")
        return False

if __name__ == "__main__":
    print("Running import conversion tests...\n")
    
    tests = [
        test_new_import_pattern,
        test_backward_compatibility,
        test_class_identity,
        test_no_conflicts,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print(f"\n{'='*50}")
    print(f"Test Results: {sum(results)}/{len(results)} tests passed")
    
    if all(results):
        print("✓ All tests passed! Import conversion is working correctly.")
        sys.exit(0)
    else:
        print("✗ Some tests failed. Please check the implementation.")
        sys.exit(1)