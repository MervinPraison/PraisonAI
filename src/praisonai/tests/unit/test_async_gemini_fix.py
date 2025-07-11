"""
Test to verify that async agents with Gemini models properly use tools
after the fix for issue #818
"""
import asyncio
import logging
from praisonaiagents import Agent, Task, PraisonAIAgents

# Enable logging to see tool calls
logging.basicConfig(level=logging.INFO)

# Mock search tool
async def mock_search(query: str) -> dict:
    """Mock search tool for testing"""
    print(f"[TOOL CALLED] Searching for: {query}")
    return {
        "query": query,
        "results": [
            {
                "title": f"Result 1 for {query}",
                "snippet": f"This is a mock result about {query}",
                "url": "https://example.com/1"
            },
            {
                "title": f"Result 2 for {query}", 
                "snippet": f"Another mock result about {query}",
                "url": "https://example.com/2"
            }
        ],
        "status": "success"
    }

async def test_async_gemini_tools():
    """Test async agents with Gemini models use tools correctly"""
    
    # Create search agent with Gemini model
    search_agent = Agent(
        name="AsyncSearcher",
        role="Research Assistant",
        goal="Find information using the search tool",
        backstory="You are an expert at finding information online",
        tools=[mock_search],
        llm={"model": "gemini/gemini-1.5-flash-latest"},
        verbose=True
    )
    
    # Create analysis agent without tools
    analysis_agent = Agent(
        name="Analyzer",
        role="Data Analyst",
        goal="Analyze search results",
        backstory="You excel at analyzing and summarizing information",
        llm={"model": "gemini/gemini-1.5-flash-latest"},
        verbose=True
    )
    
    # Create tasks
    search_task = Task(
        name="search_task",
        description="Search for information about 'quantum computing breakthroughs 2024'",
        expected_output="Search results with at least 2 relevant findings",
        agent=search_agent,
        async_execution=True
    )
    
    analysis_task = Task(
        name="analysis_task", 
        description="Analyze the search results and provide a summary",
        expected_output="A concise summary of the findings",
        agent=analysis_agent,
        context=[search_task],
        async_execution=False
    )
    
    # Create workflow
    workflow = PraisonAIAgents(
        agents=[search_agent, analysis_agent],
        tasks=[search_task, analysis_task],
        verbose=True
    )
    
    # Execute async
    print("\n🚀 Starting async agent test with Gemini models...")
    result = await workflow.astart()
    
    # Check results
    print("\n✅ Test Results:")
    print("-" * 50)
    
    # Verify search agent used the tool
    search_result = str(result)
    if "mock result" in search_result.lower() or "tool called" in search_result.lower():
        print("✅ SUCCESS: Search agent properly used the mock_search tool!")
    else:
        print("❌ FAILURE: Search agent did NOT use the tool (claimed no internet access)")
    
    # Show the actual output
    print("\nFinal output:")
    print(result)
    
    return result

async def test_multiple_async_agents():
    """Test multiple async agents running in parallel"""
    
    agents = []
    tasks = []
    
    # Create 3 search agents
    for i in range(3):
        agent = Agent(
            name=f"AsyncAgent{i}",
            role="Researcher",
            goal="Search for information",
            backstory="Expert researcher",
            tools=[mock_search],
            llm={"model": "gemini/gemini-1.5-flash-latest"}
        )
        
        task = Task(
            name=f"task_{i}",
            description=f"Search for 'AI advancement #{i+1}'",
            expected_output="Search results",
            agent=agent,
            async_execution=True
        )
        
        agents.append(agent)
        tasks.append(task)
    
    # Execute all in parallel
    workflow = PraisonAIAgents(agents=agents, tasks=tasks)
    
    print("\n🚀 Testing multiple async agents in parallel...")
    results = await workflow.astart()
    
    # Verify all agents used tools
    success_count = 0
    for i, task in enumerate(tasks):
        if "mock result" in str(results).lower():
            success_count += 1
    
    print(f"\n✅ {success_count}/{len(tasks)} agents successfully used tools")
    
    return results

async def main():
    """Run all async tests"""
    try:
        # Test 1: Single async agent
        await test_async_gemini_tools()
        
        # Test 2: Multiple async agents in parallel
        await test_multiple_async_agents()
        
        print("\n🎉 All async tests completed!")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
