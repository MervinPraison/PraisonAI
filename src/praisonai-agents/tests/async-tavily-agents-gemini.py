import asyncio
import logging
from typing import List, Dict, Any
from pydantic import BaseModel
from praisonaiagents import Agent, Task, PraisonAIAgents, TaskOutput
from tavily import AsyncTavilyClient

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

llm_config = {
    "model": "gemini/gemini-1.5-flash-8b",
    "response_format": {
        "type": "text"
    }
}

# Define output model
class SearchResult(BaseModel):
    query: str
    results: List[Dict[str, Any]]
    total_results: int

# Define Tavily search tool
async def tavily_search(query) -> Dict[str, Any]:
    """Async Tavily search tool that returns structured results"""
    client = AsyncTavilyClient()
    try:
        results = await client.search(query)
        print(f"Tavily search results: {results}")
        return {
            "query": query,
            "results": results.get("results", []),
            "total_results": len(results.get("results", []))
        }
    except Exception as e:
        logging.error(f"Tavily search error: {e}")
        return {
            "query": query,
            "results": [],
            "total_results": 0
        }

# Define async callback
async def async_callback(output: TaskOutput):
    if output.output_format == "JSON":
        logging.info(f"Search completed: {output.json_dict.get('query', '')}")
    elif output.output_format == "Pydantic":
        logging.info(f"Search completed: {output.pydantic}")

async def run_parallel_searches():
    # Create search agent with direct tool function
    search_agent = Agent(
        name="TavilySearchAgent",
        role="Search Specialist",
        goal="Perform parallel web searches with high accuracy",
        backstory="Expert in web search and information retrieval",
        tools=[tavily_search],
        llm=llm_config
    )
    
    # Create summary agent
    summary_agent = Agent(
        name="ContentSynthesizer",
        role="Research Analyst",
        goal="Synthesize search results into coherent insights",
        backstory="Expert in analyzing and combining multiple sources of information",
        llm=llm_config
    )
    
    # Define search topics
    search_topics = [
        "Latest AI breakthroughs 2024",
        "Future of quantum computing",
        "Advancements in robotics"
    ]
    
    # Create parallel search tasks
    search_tasks = [
        Task(
            name=f"search_{i}",
            description=f"Search and analyze: {topic}",
            expected_output="Comprehensive search results with analysis",
            agent=search_agent,
            async_execution=True,
            callback=async_callback,
        ) for i, topic in enumerate(search_topics)
    ]
    
    # Create summary task
    summary_task = Task(
        name="synthesize_results",
        description="Create a comprehensive summary of all search findings",
        expected_output="Synthesized insights from all searches",
        agent=summary_agent,
        async_execution=False,
        context=search_tasks
    )
    
    # Initialize agents manager
    agents = PraisonAIAgents(
        agents=[search_agent, summary_agent],
        tasks=search_tasks + [summary_task]
    )
    
    # Execute tasks
    results = await agents.astart()
    return {
        "search_results": [str(results["task_results"][i]) for i in range(len(search_tasks))],
        "summary": str(results["task_results"][summary_task.id]),
        "topics": search_topics
    }

async def main():
    try:
        logging.info("Starting parallel Tavily searches...")
        results = await run_parallel_searches()
        logging.info("Search process completed successfully")
        print("\nResults Summary:")
        for topic, result in zip(results["topics"], results["search_results"]):
            print(f"\n{topic}:\n{result}")
        print(f"\nFinal Summary:\n{results['summary']}")
    except Exception as e:
        logging.error(f"Error in execution: {e}")

if __name__ == "__main__":
    asyncio.run(main())
