"""
Example: Using Latency Tracking Tool with PraisonAI

This example shows how to track latency without modifying core files.
"""

from praisonaiagents import Agent, PraisonAIAgents
from latency_tracker_tool import (
    latency_tracking_tool, 
    create_tracked_agent,
    create_tracked_llm,
    tracker,
    get_latency_metrics,
    get_latency_summary
)
import json


# Example 1: Using the latency tracking tool directly with agents
def example_with_tool():
    """Example using latency_tracking_tool as a custom tool."""
    print("=== Example 1: Using Latency Tracking Tool ===\n")
    
    # Create an agent with the latency tracking tool
    researcher = Agent(
        name="Researcher",
        role="Information Researcher",
        goal="Research and provide information",
        tools=[latency_tracking_tool],  # Add our custom tool
        llm="gpt-5-nano"
    )
    
    # Start tracking manually
    latency_tracking_tool("start", "planning", "request_1")
    
    # Agent performs task
    response = researcher.chat("What is the capital of France?")
    
    # End tracking
    latency_tracking_tool("end", "planning", "request_1")
    
    # Get metrics
    metrics_json = latency_tracking_tool("metrics", request_id="request_1")
    metrics = json.loads(metrics_json)
    
    print(f"Response: {response}")
    print(f"Metrics: {json.dumps(metrics, indent=2)}")


# Example 2: Using wrapper classes for automatic tracking
def example_with_wrappers():
    """Example using wrapper classes for automatic tracking."""
    print("\n=== Example 2: Using Wrapper Classes ===\n")
    
    # Create tracked agent class
    TrackedAgent = create_tracked_agent(Agent)
    
    # Create agent with tracking
    analyst = TrackedAgent(
        name="Analyst",
        role="Data Analyst",
        goal="Analyze data and provide insights",
        llm="gpt-5-nano",
        request_id="request_2"  # Unique request ID
    )
    
    # Operations are automatically tracked
    response = analyst.chat("Calculate the sum of 1 to 10")
    
    # Get metrics
    metrics = get_latency_metrics("request_2")
    
    print(f"Response: {response}")
    print(f"Metrics: {json.dumps(metrics, indent=2)}")


# Example 3: Using context manager for fine-grained tracking
def example_with_context_manager():
    """Example using context manager for custom phase tracking."""
    print("\n=== Example 3: Using Context Manager ===\n")
    
    agent = Agent(
        name="Calculator",
        role="Math Expert",
        goal="Solve mathematical problems",
        llm="gpt-5-nano"
    )
    
    request_id = "request_3"
    
    # Track different phases manually
    with tracker.track("initialization", request_id):
        # Simulate initialization
        pass
    
    with tracker.track("planning", request_id):
        response = agent.chat("What is 15% of 200?")
    
    with tracker.track("post_processing", request_id):
        # Simulate post-processing
        result = f"Formatted result: {response}"
    
    # Get comprehensive metrics
    metrics = get_latency_metrics(request_id)
    
    print(f"Result: {result}")
    print(f"Metrics by phase:")
    for phase, data in metrics.items():
        print(f"  {phase}: {data['total']:.3f}s")


# Example 4: Tracking MCP server requests
def example_mcp_tracking():
    """Example for tracking MCP server operations."""
    print("\n=== Example 4: MCP Server Tracking ===\n")
    
    # Simulate MCP server request handling
    request_id = "mcp_request_1"
    
    # Start tracking the entire request
    with tracker.track("total_request", request_id):
        
        # Track planning phase
        with tracker.track("planning", request_id):
            agent = Agent(
                name="Assistant",
                role="MCP Assistant",
                goal="Handle MCP requests",
                llm="gpt-5-nano"
            )
            plan = agent.chat("Plan: Search for Python documentation")
        
        # Track tool usage (this will now have actual timing)
        with tracker.track("tool_usage", request_id):
            # Simulate tool execution with realistic timing
            import time
            time.sleep(0.1)  # Simulate some work
            tool_result = "Found 5 relevant documentation pages"
        
        # Track LLM generation
        with tracker.track("llm_generation", request_id):
            final_response = agent.chat(f"Based on {tool_result}, provide a summary")
    
    # Get detailed metrics
    metrics = get_latency_metrics(request_id)
    
    print("MCP Request Metrics:")
    print(f"Total time: {metrics['total_request']['total']:.3f}s")
    print(f"Breakdown:")
    for phase in ['planning', 'tool_usage', 'llm_generation']:
        if phase in metrics:
            print(f"  - {phase}: {metrics[phase]['total']:.3f}s")


# Example 5: Tracking multiple concurrent requests
def example_concurrent_tracking():
    """Example tracking multiple concurrent requests."""
    print("\n=== Example 5: Concurrent Request Tracking ===\n")
    
    # Simulate multiple MCP requests
    for i in range(3):
        request_id = f"concurrent_{i}"
        
        with tracker.track("total", request_id):
            agent = Agent(
                name=f"Agent_{i}",
                role="Concurrent Worker",
                goal="Process requests concurrently",
                llm="gpt-5-nano"
            )
            
            with tracker.track("processing", request_id):
                agent.chat(f"Process request {i}")
    
    # Get summary of all requests
    summary = get_latency_summary()
    
    print("Summary of all requests:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    # Run all examples
    example_with_tool()
    example_with_wrappers()
    example_with_context_manager()
    example_mcp_tracking()
    example_concurrent_tracking()
    
    # Final summary
    print("\n=== Final Summary ===")
    final_summary = get_latency_summary()
    print(f"Total requests tracked: {len(final_summary)}")
    
    # Clear all tracking data
    tracker.clear()
    print("\nAll tracking data cleared.")