import asyncio
import time
from typing import List, Dict
from praisonaiagents import Agent, Task, PraisonAIAgents, TaskOutput
from praisonaiagents.main import (
    display_error,
    display_interaction,
    display_tool_call,
    display_instruction,
    error_logs,
    Console
)
from duckduckgo_search import DDGS
from pydantic import BaseModel

console = Console()

# 1. Define output model for structured results
class SearchResult(BaseModel):
    query: str
    results: List[Dict[str, str]]
    total_results: int

# 2. Define both sync and async tools
def sync_search_tool(query: str) -> List[Dict]:
    """
    Synchronous search using DuckDuckGo.
    Args:
        query (str): The search query.
    Returns:
        list: Search results
    """
    display_tool_call(f"Running sync search for: {query}", console)
    time.sleep(1)  # Simulate network delay
    try:
        results = []
        ddgs = DDGS()
        for result in ddgs.text(keywords=query, max_results=5):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "snippet": result.get("body", "")
            })
        return results
    except Exception as e:
        error_msg = f"Error during sync search: {e}"
        display_error(error_msg, console)
        error_logs.append(error_msg)
        return []

async def async_search_tool(query: str) -> List[Dict]:
    """
    Asynchronous search using DuckDuckGo.
    Args:
        query (str): The search query.
    Returns:
        list: Search results
    """
    display_tool_call(f"Running async search for: {query}", console)
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
        return results
    except Exception as e:
        error_msg = f"Error during async search: {e}"
        display_error(error_msg, console)
        error_logs.append(error_msg)
        return []

# 3. Define both sync and async callbacks
def sync_callback(output: TaskOutput):
    display_interaction("Sync Callback", f"Processing output: {output.raw[:100]}...", markdown=True, console=console)
    time.sleep(1)  # Simulate processing
    if output.output_format == "JSON":
        display_tool_call(f"Processed JSON result: {output.json_dict}", console)
    elif output.output_format == "Pydantic":
        display_tool_call(f"Processed Pydantic result: {output.pydantic}", console)

async def async_callback(output: TaskOutput):
    display_interaction("Async Callback", f"Processing output: {output.raw[:100]}...", markdown=True, console=console)
    await asyncio.sleep(1)  # Simulate processing
    if output.output_format == "JSON":
        display_tool_call(f"Processed JSON result: {output.json_dict}", console)
    elif output.output_format == "Pydantic":
        display_tool_call(f"Processed Pydantic result: {output.pydantic}", console)

# 4. Create agents with different tools
sync_agent = Agent(
    name="SyncAgent",
    role="Synchronous Search Specialist",
    goal="Perform synchronous searches and return structured results",
    backstory="Expert in sync operations and data organization",
    tools=[sync_search_tool],
    self_reflect=False,
    verbose=True,
    markdown=True
)

async_agent = Agent(
    name="AsyncAgent",
    role="Asynchronous Search Specialist",
    goal="Perform asynchronous searches and return structured results",
    backstory="Expert in async operations and data organization",
    tools=[async_search_tool],
    self_reflect=False,
    verbose=True,
    markdown=True
)

# 5. Create tasks with different configurations
sync_task = Task(
    name="sync_search",
    description="Search for 'Python programming' using sync tool and return structured results",
    expected_output="SearchResult model with query details and results",
    agent=sync_agent,
    async_execution=False,
    callback=sync_callback,
    output_pydantic=SearchResult
)

async_task = Task(
    name="async_search",
    description="Search for 'Async programming' using async tool and return structured results",
    expected_output="SearchResult model with query details and results",
    agent=async_agent,
    async_execution=True,
    callback=async_callback,
    output_pydantic=SearchResult
)

# 6. Create workflow tasks
workflow_sync_task = Task(
    name="workflow_sync",
    description="Workflow sync search for 'AI trends' with structured output",
    expected_output="SearchResult model with AI trends data",
    agent=sync_agent,
    async_execution=False,
    is_start=True,
    next_tasks=["workflow_async"],
    output_pydantic=SearchResult
)

workflow_async_task = Task(
    name="workflow_async",
    description="Workflow async search for 'Future of AI' with structured output",
    expected_output="SearchResult model with Future of AI data",
    agent=async_agent,
    async_execution=True,
    output_pydantic=SearchResult
)

# 7. Example usage functions
def run_sync_example():
    """Run synchronous example"""
    display_instruction("\nRunning Synchronous Example...", console)
    agents = PraisonAIAgents(
        agents=[sync_agent],
        tasks=[sync_task],
        verbose=1,
        process="sequential"
    )
    result = agents.start()
    display_interaction("Sync Example", f"Result: {result}", markdown=True, console=console)

async def run_async_example():
    """Run asynchronous example"""
    display_instruction("\nRunning Asynchronous Example...", console)
    agents = PraisonAIAgents(
        agents=[async_agent],
        tasks=[async_task],
        verbose=1,
        process="sequential"
    )
    result = await agents.astart()
    display_interaction("Async Example", f"Result: {result}", markdown=True, console=console)

async def run_mixed_example():
    """Run mixed sync/async example"""
    display_instruction("\nRunning Mixed Sync/Async Example...", console)
    agents = PraisonAIAgents(
        agents=[sync_agent, async_agent],
        tasks=[sync_task, async_task],
        verbose=1,
        process="sequential"
    )
    result = await agents.astart()
    display_interaction("Mixed Example", f"Result: {result}", markdown=True, console=console)

async def run_workflow_example():
    """Run workflow example with both sync and async tasks"""
    display_instruction("\nRunning Workflow Example...", console)
    agents = PraisonAIAgents(
        agents=[sync_agent, async_agent],
        tasks=[workflow_sync_task, workflow_async_task],
        verbose=1,
        process="workflow"
    )
    result = await agents.astart()
    display_interaction("Workflow Example", f"Result: {result}", markdown=True, console=console)

# 8. Main execution
async def main():
    """Main execution function"""
    display_instruction("Starting PraisonAI Agents Examples...", console)
    
    try:
        # Run sync example in a separate thread to not block the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_sync_example)
        
        # Run async examples
        await run_async_example()
        await run_mixed_example()
        await run_workflow_example()

        if error_logs:
            display_error("\nErrors encountered during execution:", console)
            for error in error_logs:
                display_error(error, console)
    except Exception as e:
        display_error(f"Error in main execution: {e}", console)
        error_logs.append(str(e))

if __name__ == "__main__":
    # Run the main function
    asyncio.run(main()) 