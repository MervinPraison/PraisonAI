#!/usr/bin/env python3
"""
Test script to verify the sequential thinking fix is working correctly.
This reproduces the issue described in GitHub issue #587.
"""

import sys
import os

# Add the source directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'praisonai-agents'))

from praisonaiagents import Agent, MCP

def test_sequential_thinking():
    """Test that sequential thinking continues through all planned thoughts."""
    print("Testing Sequential Thinking MCP Fix...")
    print("=" * 50)
    
    # Create agent with sequential thinking MCP tool
    sequential_agent = Agent(
        instructions="""You are a helpful assistant that can break down complex problems.
        Use the available tools when relevant to perform step-by-step analysis.""",
        llm="gpt-4o-mini",
        tools=MCP("npx -y @modelcontextprotocol/server-sequential-thinking"),
        verbose=True
    )
    
    # Test the sequential thinking
    print("Starting sequential thinking test...")
    response = sequential_agent.start("Break down the process of making a cup of tea")
    
    print("\nResponse received:")
    print(response)
    print("\n" + "=" * 50)
    print("Test completed. Check the output above to see if all 5 thoughts were processed.")

if __name__ == "__main__":
    test_sequential_thinking()