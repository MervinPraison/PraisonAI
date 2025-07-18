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
    print("Test completed successfully")

if __name__ == "__main__":
    test_termination()
    print("SUCCESS: Program terminated properly")