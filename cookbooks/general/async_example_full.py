import asyncio
import time
from typing import List, Dict
from praisonaiagents import Agent, Task, PraisonAIAgents, TaskOutput
from duckduckgo_search import DDGS
from pydantic import BaseModel

# 1. Define output model for structured results
class SearchResult(BaseModel):
    query: str
    results: List[Dict[str, str]]
    total_results: int

# 2. Define async tool
async def async_search_tool(query: str) -> Dict:
    """Perform asynchronous search and return structured results."""
    await asyncio.sleep(1)  # Simulate network delay
    try:
        results = []
        ddgs = DDGS()
        for result in ddgs.text(keywords=query, max_results=5):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "snippet": result.get("body", "")
            })
        
        return {
            "query": query,
            "results": results,
            "total_results": len(results)
        }
    except Exception as e:
        print(f"Error during async search: {e}")
        return {
            "query": query,
            "results": [],
            "total_results": 0
        }

# 3. Define async callback
async def async_callback(output: TaskOutput):
    await asyncio.sleep(1)  # Simulate processing
    if output.output_format == "JSON":
        print(f"Processed JSON result: {output.json_dict}")
    elif output.output_format == "Pydantic":
        print(f"Processed Pydantic result: {output.pydantic}")

# 4. Create specialized agents
async_agent = Agent(
    name="AsyncSearchAgent",
    role="Search Specialist",
    goal="Perform fast parallel searches with structured results",
    backstory="Expert in efficient data retrieval and parallel search operations",
    tools=[async_search_tool],
    self_reflect=False,
    verbose=True,
    markdown=True
)

summary_agent = Agent(
    name="SummaryAgent",
    role="Research Synthesizer",
    goal="Create concise summaries from multiple search results",
    backstory="Expert in analyzing and synthesizing information from multiple sources",
    self_reflect=True,
    verbose=True,
    markdown=True
)

# 5. Create async tasks
async_task = Task(
    name="async_search",
    description="Search for 'Async programming' and return results in JSON format with query, results array, and total_results count.",
    expected_output="SearchResult model with structured data",
    agent=async_agent,
    async_execution=True,
    callback=async_callback,
    output_json=SearchResult
)

async def run_parallel_tasks():
    """Run multiple async tasks in parallel"""
    print("\nRunning Parallel Async Tasks...")
    
    # Define different search topics
    search_topics = [
        "Latest AI Developments 2024",
        "Machine Learning Best Practices",
        "Neural Networks Architecture"
    ]
    
    # Create tasks for different topics
    parallel_tasks = [
        Task(
            name=f"search_task_{i}",
            description=f"Search for '{topic}' and return structured results with query details and findings.",
            expected_output="SearchResult model with search data",
            agent=async_agent,
            async_execution=True,
            callback=async_callback,
            output_json=SearchResult
        ) for i, topic in enumerate(search_topics)
    ]
    
    # Create summarization task
    summary_task = Task(
        name="summary_task",
        description="Analyze all search results and create a concise summary highlighting key findings, patterns, and implications.",
        expected_output="Structured summary with key findings and insights",
        agent=summary_agent,
        async_execution=False,
        callback=async_callback,
        context=parallel_tasks
    )
    
    # Create a single PraisonAIAgents instance with both agents
    agents = PraisonAIAgents(
        agents=[async_agent, summary_agent],
        tasks=parallel_tasks + [summary_task],
        verbose=1,
        process="sequential"
    )
    
    # Run all tasks
    results = await agents.astart()
    print(f"Tasks Results: {results}")
    
    # Return results in a serializable format
    return {
        "search_results": {
            "task_status": {k: v for k, v in results["task_status"].items() if k != summary_task.id},
            "task_results": [str(results["task_results"][i]) if results["task_results"][i] else None 
                           for i in range(len(parallel_tasks))]
        },
        "summary": str(results["task_results"][summary_task.id]) if results["task_results"].get(summary_task.id) else None,
        "topics": search_topics
    }

# 6. Main execution
async def main():
    """Main execution function"""
    print("Starting Async AI Agents Examples...")
    
    try:
        await run_parallel_tasks()
    except Exception as e:
        print(f"Error in main execution: {e}")

if __name__ == "__main__":
    # Run the main function
    asyncio.run(main())
