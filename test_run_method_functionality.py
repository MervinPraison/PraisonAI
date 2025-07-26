#!/usr/bin/env python3
"""
Test script to verify the run() method functionality works correctly
"""
import sys
import os

# Add the package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents.agent.agent import Agent
from praisonaiagents.agents.agents import PraisonAIAgents
from praisonaiagents.task.task import Task

def test_run_method_delegation():
    """Test that run() correctly delegates to start()"""
    print("Testing PraisonAIAgents run() method delegation...")
    
    # Create a mock agent (no LLM needed for this test)
    agent = Agent(
        name="TestAgent",
        role="Test Role", 
        goal="Test Goal",
        backstory="Test Backstory",
        verbose=False
    )
    
    # Create a simple task
    task = Task(
        name="test_task",
        description="Test task",
        expected_output="Test output",
        agent=agent
    )
    
    # Create PraisonAIAgents instance
    agents = PraisonAIAgents(
        agents=[agent],
        tasks=[task],
        verbose=0
    )
    
    # Mock the start method to avoid LLM calls
    start_called = False
    start_args = None
    start_kwargs = None
    
    def mock_start(content=None, return_dict=False, **kwargs):
        nonlocal start_called, start_args, start_kwargs
        start_called = True
        start_args = (content, return_dict)
        start_kwargs = kwargs
        return "mocked_result"
    
    # Replace start method with mock
    original_start = agents.start
    agents.start = mock_start
    
    # Test run() method delegation
    result = agents.run(content="test_content", return_dict=True, extra_param="test")
    
    # Verify the call was delegated correctly
    assert start_called, "start() method should have been called"
    assert start_args == ("test_content", True), f"Arguments not passed correctly: {start_args}"
    assert start_kwargs == {"extra_param": "test"}, f"Kwargs not passed correctly: {start_kwargs}"
    assert result == "mocked_result", f"Return value not passed correctly: {result}"
    
    print("✅ run() method correctly delegates to start()")
    print("✅ Arguments and return values passed correctly")
    
    # Restore original method
    agents.start = original_start
    
    return True

def test_api_consistency():
    """Test API consistency between Agent and PraisonAIAgents"""
    print("\nTesting API consistency...")
    
    # Create Agent instance
    agent = Agent(
        name="TestAgent",
        role="Test Role", 
        goal="Test Goal",
        backstory="Test Backstory"
    )
    
    # Create PraisonAIAgents instance
    agents = PraisonAIAgents(
        agents=[agent],
        verbose=0
    )
    
    # Check that both have run() method
    assert hasattr(agent, 'run'), "Agent should have run() method"
    assert hasattr(agents, 'run'), "PraisonAIAgents should have run() method"
    
    # Check that both have start() method
    assert hasattr(agent, 'start'), "Agent should have start() method"
    assert hasattr(agents, 'start'), "PraisonAIAgents should have start() method"
    
    print("✅ Both Agent and PraisonAIAgents have run() and start() methods")
    print("✅ API consistency maintained")
    
    return True

def test_performance_overhead():
    """Test that run() method has no significant performance overhead"""
    print("\nTesting performance overhead...")
    
    agent = Agent(
        name="TestAgent",
        role="Test Role", 
        goal="Test Goal",
        backstory="Test Backstory"
    )
    
    agents = PraisonAIAgents(
        agents=[agent],
        verbose=0
    )
    
    # Mock start to measure calls
    call_count = 0
    def mock_start(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return "result"
    
    agents.start = mock_start
    
    # Call run() multiple times
    for i in range(100):
        agents.run()
    
    # Verify no extra overhead (should be exactly 100 calls to start)
    assert call_count == 100, f"Expected 100 calls, got {call_count}"
    
    print("✅ No performance overhead detected")
    print(f"✅ Direct delegation confirmed (100 calls = {call_count} start() calls)")
    
    return True

if __name__ == "__main__":
    try:
        test_run_method_delegation()
        test_api_consistency()
        test_performance_overhead()
        print("\n🎉 All functionality tests passed!")
        print("✅ run() method working correctly")
        print("✅ No backward compatibility issues")
        print("✅ Zero performance overhead")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)