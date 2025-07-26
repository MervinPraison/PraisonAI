import asyncio
import logging
from typing import List, Dict, Any
from pydantic import BaseModel
from praisonaiagents import Agent, Task, PraisonAIAgents, TaskOutput
from tavily import AsyncTavilyClient
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

llm_config = {
    "model": "gpt-4o-mini",  # Changed from Gemini to GPT-4o-mini for better tool support
    "temperature": 0.7,
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
async def tavily_search(query: str) -> Dict[str, Any]:
    """
    Async Tavily search tool that returns structured results
    
    Args:
        query: The search query string
        
    Returns:
        Dict containing search results
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        logging.error("TAVILY_API_KEY not found in environment variables")
        return {
            "query": query,
            "results": [],
            "total_results": 0,
            "error": "TAVILY_API_KEY not configured"
        }
    
    logging.info(f"Executing Tavily search for: {query}")
    client = AsyncTavilyClient(api_key=api_key)
    try:
        results = await client.search(query)
        logging.info(f"Tavily search completed successfully for: {query}")
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
        backstory="Expert in web search and information retrieval. You have access to the tavily_search tool to search the web.",
        tools=[tavily_search],
        llm=llm_config,
        verbose=True
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
            description=f"Use the tavily_search tool to search for information about: {topic}. You must call the tavily_search function with the query '{topic}'",
            expected_output="Comprehensive search results with analysis from the tavily_search tool",
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
    
    # Execute tasks - FIXED: Added return_dict=True
    results = await agents.astart(return_dict=True)
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
