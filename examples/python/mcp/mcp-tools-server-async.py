"""MCP Tools Server with Async Functions

Example showing how to expose async Python functions as MCP tools.

Usage:
    python mcp-tools-server-async.py
"""

import asyncio
from praisonaiagents.mcp import ToolsMCPServer


async def async_search(query: str, delay: float = 0.1) -> dict:
    """Async search function.
    
    Args:
        query: The search query
        delay: Simulated delay in seconds
    """
    await asyncio.sleep(delay)  # Simulate async operation
    return {
        "query": query,
        "results": [f"Async result for {query}"]
    }


async def async_fetch_url(url: str) -> dict:
    """Fetch content from a URL asynchronously.
    
    Args:
        url: The URL to fetch
    """
    # Mock implementation - use aiohttp in production
    await asyncio.sleep(0.1)
    return {
        "url": url,
        "status": 200,
        "content": f"Content from {url}"
    }


async def async_process_data(data: str, iterations: int = 3) -> dict:
    """Process data asynchronously with multiple iterations.
    
    Args:
        data: The data to process
        iterations: Number of processing iterations
    """
    results = []
    for i in range(iterations):
        await asyncio.sleep(0.05)
        results.append(f"Iteration {i+1}: processed {data}")
    
    return {
        "input": data,
        "iterations": iterations,
        "results": results
    }


# Sync function can also be mixed with async
def sync_calculate(a: int, b: int) -> dict:
    """Synchronous calculation (can be mixed with async tools)."""
    return {"sum": a + b, "product": a * b}


if __name__ == "__main__":
    server = ToolsMCPServer(name="async-tools-server")
    
    # Register both async and sync tools
    server.register_tools([
        async_search,
        async_fetch_url,
        async_process_data,
        sync_calculate
    ])
    
    print(f"Registered tools: {server.get_tool_names()}")
    server.run()
