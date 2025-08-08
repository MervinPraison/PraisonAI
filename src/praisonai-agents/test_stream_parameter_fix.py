#!/usr/bin/env python3
"""
Test to verify that the stream parameter is correctly passed through the agent.chat() method.
This tests the fix for the issue where stream=self.stream was being used instead of the passed parameter.
"""

import os
from praisonaiagents import Agent

# Use a simple model for testing
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "test-key")

def test_stream_parameter():
    """Test that stream parameter is correctly passed through chat method"""
    
    # Create an agent with stream=True by default
    agent = Agent(
        name="TestAgent",
        role="Test Assistant",
        goal="Test streaming behavior",
        backstory="A test agent for verifying stream parameter handling",
        llm="gpt-5-nano",
        stream=True,  # Default to streaming
        verbose=True
    )
    
    print("Test 1: Agent has stream=True, but we pass stream=False to chat()")
    print("Expected: Should NOT stream (no progressive display)")
    print("-" * 50)
    
    # Call chat with stream=False explicitly - should override agent's stream=True
    response1 = agent.chat("Tell me a very short fact about Python in one sentence.", stream=False)
    print(f"\nResponse 1: {response1}")
    
    print("\n" + "="*70 + "\n")
    
    print("Test 2: Agent has stream=True, and we pass stream=True to chat()")
    print("Expected: Should stream (progressive display)")
    print("-" * 50)
    
    # Call chat with stream=True explicitly - should stream
    response2 = agent.chat("Tell me another very short fact about Python in one sentence.", stream=True)
    print(f"\nResponse 2: {response2}")
    
    print("\n" + "="*70 + "\n")
    
    # Now test with an agent that has stream=False by default
    agent2 = Agent(
        name="TestAgent2",
        role="Test Assistant 2",
        goal="Test non-streaming behavior",
        backstory="A test agent for verifying non-stream parameter handling",
        llm="gpt-5-nano",
        stream=False,  # Default to non-streaming
        verbose=True
    )
    
    print("Test 3: Agent has stream=False, but we pass stream=True to chat()")
    print("Expected: Should stream (progressive display)")
    print("-" * 50)
    
    # Call chat with stream=True explicitly - should override agent's stream=False
    response3 = agent2.chat("Tell me a very short fact about JavaScript in one sentence.", stream=True)
    print(f"\nResponse 3: {response3}")
    
    print("\n" + "="*70 + "\n")
    
    print("Test 4: Agent has stream=False, and we don't pass stream to chat()")
    print("Expected: Should NOT stream (uses agent's default)")
    print("-" * 50)
    
    # Call chat without stream parameter - should use agent's default (False)
    response4 = agent2.chat("Tell me a very short fact about Java in one sentence.")
    print(f"\nResponse 4: {response4}")
    
    print("\n" + "="*70 + "\n")
    print("All tests completed!")

if __name__ == "__main__":
    test_stream_parameter()