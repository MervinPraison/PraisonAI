#!/usr/bin/env python3
"""
Test different combinations of verbose and stream parameters to understand the display behavior.
"""

import os
from praisonaiagents import Agent

# Use a simple model for testing
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "test-key")

def test_combination(verbose: bool, stream: bool, test_name: str):
    """Test a specific combination of verbose and stream settings"""
    print(f"\n{'='*70}")
    print(f"Test: {test_name}")
    print(f"Settings: verbose={verbose}, stream={stream}")
    print(f"{'='*70}\n")
    
    agent = Agent(
        name="TestAgent",
        role="Test Assistant",
        goal="Test display behavior",
        backstory="A test agent",
        llm="gpt-5-nano",
        verbose=verbose,
        stream=stream
    )
    
    response = agent.chat("What is 2 + 2? Answer in exactly one word.")
    print(f"\nFinal response: {response}")
    print(f"\n{'-'*70}")

def main():
    print("Testing different combinations of verbose and stream settings")
    print("Observing the display behavior for each combination\n")
    
    # Test all 4 combinations
    test_combination(verbose=True, stream=True, test_name="Verbose ON, Stream ON")
    test_combination(verbose=True, stream=False, test_name="Verbose ON, Stream OFF")
    test_combination(verbose=False, stream=True, test_name="Verbose OFF, Stream ON")
    test_combination(verbose=False, stream=False, test_name="Verbose OFF, Stream OFF")
    
    print("\n\nNow testing with explicit stream parameter in chat() method:")
    
    # Test overriding stream in chat method
    print(f"\n{'='*70}")
    print("Test: Agent has stream=True, but chat() called with stream=False")
    print(f"{'='*70}\n")
    
    agent = Agent(
        name="TestAgent",
        role="Test Assistant",
        goal="Test display behavior",
        backstory="A test agent",
        llm="gpt-5-nano",
        verbose=True,
        stream=True  # Agent default is streaming
    )
    
    # Override with stream=False in chat
    response = agent.chat("What is 3 + 3? Answer in exactly one word.", stream=False)
    print(f"\nFinal response: {response}")
    
    print("\n\nAll tests completed!")

if __name__ == "__main__":
    main()