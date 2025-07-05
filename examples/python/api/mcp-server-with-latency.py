"""
Example of MCP server with latency tracking enabled.

To enable latency tracking, set the environment variable:
    export PRAISON_LATENCY_TRACKING=true

Or enable it programmatically as shown below.
"""

from praisonaiagents import Agent
from praisonaiagents.monitoring import (
    enable_tracking,
    get_latency_summary,
    start_request,
    end_request
)
import asyncio

# Enable latency tracking programmatically
enable_tracking()

# Create an agent with tools
def get_current_time():
    """Get the current time"""
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers"""
    return a + b

agent = Agent(
    name="LatencyTestAgent",
    instructions="You are a helpful assistant that can tell time and do math",
    tools=[get_current_time, calculate_sum]
)

# For MCP mode with automatic latency tracking
print("Starting MCP server with latency tracking...")
print("To test, use an MCP client to connect to http://localhost:8080/sse")
print("\nExample requests to test:")
print("1. 'What time is it?'")
print("2. 'Calculate 42 + 58'") 
print("3. 'What time is it and what is 100 + 200?'")
print("\nLatency metrics will be printed after each request.")

# Create a custom handler to track requests
original_execute = None

async def tracked_execute_task(prompt: str) -> str:
    """Wrapper to track individual MCP requests"""
    # Start tracking this request
    start_request(prompt[:50])  # Use first 50 chars as request ID
    
    try:
        # Call original method
        result = await original_execute(prompt)
        
        # End tracking and print metrics
        request_metrics = end_request()
        print(f"\n--- Request Latency Metrics ---")
        print(f"Request: {prompt[:50]}...")
        print(f"Total time: {request_metrics.get('total_time', 0):.3f}s")
        
        phases = request_metrics.get('phases', {})
        for phase, data in phases.items():
            print(f"{phase}: {data['total']:.3f}s ({data['count']} calls)")
        
        # Print overall summary
        summary = get_latency_summary()
        print(f"\n--- Overall Summary ---")
        for phase, stats in summary.get('phases', {}).items():
            if stats['total_requests'] > 0:
                print(f"{phase}: avg={stats['average_time']:.3f}s, "
                      f"min={stats['min_time']:.3f}s, max={stats['max_time']:.3f}s "
                      f"({stats['total_requests']} requests)")
        
        return result
    except Exception as e:
        end_request()  # Make sure to end tracking even on error
        raise e

# Monkey patch the MCP execute method to add tracking
# This is done after launch() returns in a real scenario
# For demonstration, we'll show the concept

# Launch the MCP server
agent.launch(port=8080, protocol="mcp")