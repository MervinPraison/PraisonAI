#!/usr/bin/env python3
"""
Test script to verify the run() method functionality
"""
import sys
import os

# Add the package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.agent.agent import Agent
from praisonaiagents.agents.agents import PraisonAIAgents
from praisonaiagents.task.task import Task

def test_run_method():
    print("Testing PraisonAIAgents run() method...")
    
    # Create a simple agent
    agent = Agent(
        name="TestAgent",
        role="Test Role", 
        goal="Test Goal",
        backstory="Test Backstory",
        verbose=True
    )
    
    # Create a simple task
    task = Task(
        name="test_task",
        description="Say hello",
        expected_output="A greeting message",
        agent=agent
    )
    
    # Create PraisonAIAgents instance
    agents = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        verbose=1
    )
    
    # Test that run() method exists
    assert hasattr(agents, 'run'), "run() method should exist"
    
    # Test that start() method exists  
    assert hasattr(agents, 'start'), "start() method should exist"
    
    # Test that run() has same signature as start()
    import inspect
    run_sig = inspect.signature(agents.run)
    start_sig = inspect.signature(agents.start)
    
    assert run_sig == start_sig, f"Signatures should match: run{run_sig} vs start{start_sig}"
    
    print("✅ run() method exists and has correct signature")
    print(f"✅ run() signature: {run_sig}")
    print(f"✅ start() signature: {start_sig}")
    
    # Verify the method is correctly implemented
    assert agents.run.__doc__ is not None, "run() method should have docstring"
    assert "Alias for start()" in agents.run.__doc__, "run() should be documented as alias"
    
    print("✅ run() method is properly documented as alias")
    print("✅ All tests passed!")
    
    return True

if __name__ == "__main__":
    try:
        test_run_method()
        print("\n🎉 All tests completed successfully!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)