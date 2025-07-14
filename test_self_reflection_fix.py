#!/usr/bin/env python3
"""
Test script to verify self-reflection fix for issue #901
Tests both with and without tools to ensure fix works correctly
"""
import sys
import os
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src" / "praisonai-agents"))

from praisonaiagents import Agent, Task, PraisonAIAgents

def create_mock_tool():
    """Create a mock tool that mimics the user's custom search tool"""
    def mock_search_tool(query: str) -> str:
        """Mock tool that returns a fake search result"""
        return f"Mock search result for: {query}"
    
    # Set the function name as expected by the tool system
    mock_search_tool.__name__ = "mock_search_tool"
    
    return mock_search_tool

def test_self_reflection_with_tools():
    """Test that self-reflection works when tools are present"""
    print("Testing self-reflection WITH tools...")
    
    # Create mock tool
    mock_tool = create_mock_tool()
    
    # Create an agent with self-reflection and tools
    agent = Agent(
        role="Senior Research Analyst",
        goal="Analyze and provide insights on given topics",
        backstory="You are an expert analyst with strong critical thinking skills",
        self_reflect=True,
        llm="gpt-4o-mini",  # Using OpenAI model for testing
        verbose=True,
        tools=[mock_tool],
        max_reflect=2,  # Keep it small for testing
        min_reflect=1
    )
    
    # Create a task
    task = Task(
        description="Analyze the importance of AI in modern business",
        expected_output="A brief analysis report",
        agent=agent
    )
    
    # Create and start the agents
    try:
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            process="sequential"
        )
        
        result = agents.start()
        print(f"✅ Self-reflection with tools completed successfully!")
        print(f"Result: {result}")
        return True
    except Exception as e:
        print(f"❌ Self-reflection with tools failed: {e}")
        return False

def test_self_reflection_without_tools():
    """Test that self-reflection still works without tools (baseline)"""
    print("\nTesting self-reflection WITHOUT tools...")
    
    # Create an agent with self-reflection but no tools
    agent = Agent(
        role="Senior Research Analyst",
        goal="Analyze and provide insights on given topics",
        backstory="You are an expert analyst with strong critical thinking skills",
        self_reflect=True,
        llm="gpt-4o-mini",  # Using OpenAI model for testing
        verbose=True,
        max_reflect=2,  # Keep it small for testing
        min_reflect=1
    )
    
    # Create a task
    task = Task(
        description="Analyze the importance of AI in modern business",
        expected_output="A brief analysis report",
        agent=agent
    )
    
    # Create and start the agents
    try:
        agents = PraisonAIAgents(
            agents=[agent],
            tasks=[task],
            process="sequential"
        )
        
        result = agents.start()
        print(f"✅ Self-reflection without tools completed successfully!")
        print(f"Result: {result}")
        return True
    except Exception as e:
        print(f"❌ Self-reflection without tools failed: {e}")
        return False

def test_llm_directly():
    """Test LLM class directly to isolate the issue"""
    print("\nTesting LLM class directly...")
    
    from praisonaiagents.llm import LLM
    
    # Create mock tool
    mock_tool = create_mock_tool()
    
    # Create LLM instance
    llm = LLM(model="gpt-4o-mini")
    
    def mock_tool_executor(function_name, arguments):
        """Mock tool executor that simulates tool execution"""
        if function_name == "mock_search_tool":
            return mock_tool(arguments.get("query", "test"))
        return None
    
    try:
        # Test with tools and self-reflection
        response = llm.get_response(
            prompt="Analyze the importance of AI in modern business",
            tools=[mock_tool],
            self_reflect=True,
            max_reflect=2,
            min_reflect=1,
            verbose=True,
            execute_tool_fn=mock_tool_executor
        )
        
        print(f"✅ LLM direct test with tools completed successfully!")
        print(f"Response: {response}")
        return True
    except Exception as e:
        print(f"❌ LLM direct test with tools failed: {e}")
        return False

if __name__ == "__main__":
    # Check if we have required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY environment variable is required for testing")
        sys.exit(1)
    
    print("Testing self-reflection fix for issue #901")
    print("=" * 50)
    
    # Run tests
    test_results = []
    
    # Test 1: Without tools (baseline)
    test_results.append(test_self_reflection_without_tools())
    
    # Test 2: With tools (the fixed case)
    test_results.append(test_self_reflection_with_tools())
    
    # Test 3: Direct LLM test
    test_results.append(test_llm_directly())
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary:")
    print(f"✅ Tests passed: {sum(test_results)}")
    print(f"❌ Tests failed: {len(test_results) - sum(test_results)}")
    
    if all(test_results):
        print("🎉 All tests passed! Self-reflection fix is working correctly.")
        sys.exit(0)
    else:
        print("💥 Some tests failed. Please check the output above.")
        sys.exit(1)