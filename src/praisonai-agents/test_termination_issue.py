"""
Test script to reproduce the termination issue
"""
import sys
import os

# Add the src directory to the path so we can import praisonaiagents
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents import Agent

def test_termination():
    """Test that the agent terminates properly after execution"""
    print("Testing agent termination...")
    
    agent = Agent(instructions="You are a helpful AI assistant")
    response = agent.start("Write a short hello world message")
    
    print(f"Agent response: {response}")
    print("Agent execution completed. Testing if program terminates...")
    
    # If this completes without hanging, the fix works
    return True

if __name__ == "__main__":
    result = test_termination()
    if result:
        print("SUCCESS: Program terminated properly")
    else:
        print("FAILURE: Program did not terminate")