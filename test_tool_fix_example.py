"""
Test example demonstrating the tool call fix for Gemini models.

This example shows how agents now properly use tools instead of saying
"I do not have access to the internet".
"""
import logging
from praisonaiagents import Agent, Task, PraisonAIAgents

# Enable debug logging to see tool processing
logging.basicConfig(level=logging.DEBUG)

# Define a simple search tool (synchronous version)
def mock_search(query: str) -> str:
    """Search for information on the internet. 
    
    Args:
        query: The search query string
        
    Returns:
        Mock search results for the query
    """
    return f"Mock search results for '{query}': Found 10 relevant articles about {query}. Top result: Latest developments and breakthroughs in this field..."

# Create agent with Gemini model and the search tool
search_agent = Agent(
    name="SearchAgent",
    role="Information Researcher", 
    goal="Find accurate information using the mock_search tool",
    backstory="Expert researcher skilled at finding and analyzing information from various sources",
    tools=[mock_search],
    llm={"model": "gemini/gemini-1.5-flash-8b"},
    verbose=True
)

# Create a task that should trigger tool usage
search_task = Task(
    name="search_ai_breakthroughs",
    description="Search for information about latest AI breakthroughs in 2024",
    expected_output="A comprehensive summary of AI breakthroughs found through search",
    agent=search_agent
)

def test_tool_usage():
    """Test that the agent uses tools instead of saying it has no internet access."""
    print("=" * 60)
    print("Testing Tool Usage with Gemini Model")
    print("=" * 60)
    
    # Create workflow
    workflow = PraisonAIAgents(
        agents=[search_agent],
        tasks=[search_task],
        verbose=True
    )
    
    # Execute the workflow
    print("\nExecuting task...")
    result = workflow.start()
    
    # Check the result
    print("\n" + "=" * 60)
    print("RESULT:")
    print("=" * 60)
    
    if isinstance(result, dict) and 'task_results' in result:
        task_result = result['task_results'][0]
        print(f"Task Output: {task_result}")
        
        # Check if the agent used the tool or claimed no access
        if "do not have access" in str(task_result).lower():
            print("\n❌ FAILED: Agent still claims no internet access")
        elif "mock search results" in str(task_result).lower():
            print("\n✅ SUCCESS: Agent used the search tool!")
        else:
            print("\n⚠️  UNCLEAR: Check if agent used the tool properly")
    else:
        print(f"Result: {result}")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    # Run the test
    test_tool_usage()
    
    print("\n\nNOTE: With the fix applied, the agent should use the mock_search tool")
    print("instead of saying 'I do not have access to the internet'.")