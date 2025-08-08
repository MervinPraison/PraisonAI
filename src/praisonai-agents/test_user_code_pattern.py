#!/usr/bin/env python3
"""
Test script that replicates the exact user code pattern from issue #901
"""
import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src" / "praisonai-agents"))

from praisonaiagents import Agent, Task, PraisonAIAgents

def google_web_search_llm(query: str) -> str:
    """Mock implementation of the user's custom search tool"""
    return f"Mock Google search result for: {query}"

def test_user_code_pattern_with_tools():
    """Test the exact user code pattern WITH tools"""
    print("Testing user code pattern WITH tools...")
    
    # Create an agent with self-reflection (exact user code pattern)
    agent = Agent(
        role="Senior Research Analyst",
        goal="Analyze and provide insights on given topics",
        backstory="You are an expert analyst with strong critical thinking skills",
        self_reflect=True,
        llm="gpt-5-nano",  # Using OpenAI instead of Gemini for testing
        verbose=True,
        tools=[google_web_search_llm]
    )

    # Create a task
    task = Task(
        description="Analyze recent developments in AI",
        expected_output="A detailed analysis report",
        agent=agent
    )

    # Create and start the agents
    try:
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            process="sequential"
        )

        # Start execution
        result = agents.start()
        print("✅ User code pattern WITH tools completed successfully!")
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        return True
    except Exception as e:
        print(f"❌ User code pattern WITH tools failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_user_code_pattern_without_tools():
    """Test the exact user code pattern WITHOUT tools"""
    print("\nTesting user code pattern WITHOUT tools...")
    
    # Create an agent with self-reflection (exact user code pattern, no tools)
    agent = Agent(
        role="Senior Research Analyst",
        goal="Analyze and provide insights on given topics",
        backstory="You are an expert analyst with strong critical thinking skills",
        self_reflect=True,
        llm="gpt-5-nano",  # Using OpenAI instead of Gemini for testing
        verbose=True
    )

    # Create a task
    task = Task(
        description="Analyze recent developments in AI",
        expected_output="A detailed analysis report",
        agent=agent
    )

    # Create and start the agents
    try:
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            process="sequential"
        )

        # Start execution
        result = agents.start()
        print("✅ User code pattern WITHOUT tools completed successfully!")
        print(f"Result type: {type(result)}")
        print(f"Result: {result}")
        return True
    except Exception as e:
        print(f"❌ User code pattern WITHOUT tools failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # Check if we have required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY environment variable is required for testing")
        print("Please set it with: export OPENAI_API_KEY='your-api-key-here'")
        sys.exit(1)
    
    print("Testing exact user code pattern from issue #901")
    print("=" * 60)
    
    # Run tests
    test_results = []
    
    # Test 1: Without tools (baseline - should work)
    test_results.append(test_user_code_pattern_without_tools())
    
    # Test 2: With tools (the problematic case that should now work)
    test_results.append(test_user_code_pattern_with_tools())
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary:")
    print(f"✅ Tests passed: {sum(test_results)}")
    print(f"❌ Tests failed: {len(test_results) - sum(test_results)}")
    
    if all(test_results):
        print("🎉 All tests passed! The user's exact code pattern now works with self-reflection and tools.")
        sys.exit(0)
    else:
        print("💥 Some tests failed. The fix may not be complete.")
        sys.exit(1)