#!/usr/bin/env python3
"""
Minimal Example: Latency Tracking for MCP Server

This is the simplest way to add latency tracking to your MCP server
without modifying any core PraisonAI files.
"""

from praisonaiagents import Agent
from latency_tracker_tool import tracker
import time

# Example: Track MCP request handling
def handle_mcp_request(query: str, request_id: str = "mcp_1"):
    """Simulate handling an MCP request with latency tracking."""
    
    print(f"\nHandling MCP request: {request_id}")
    print(f"Query: {query}")
    
    # 1. Planning Phase
    tracker.start_timer("planning", request_id)
    agent = Agent(
        name="Assistant",
        role="MCP Handler",
        goal="Process requests",
        llm="gpt-4o-mini"
    )
    plan = f"I will search for information about {query}"
    time.sleep(0.1)  # Simulate planning time
    planning_time = tracker.end_timer("planning", request_id)
    
    # 2. Tool Usage Phase
    tracker.start_timer("tool_usage", request_id)
    # Simulate tool execution
    time.sleep(0.2)  # Simulate tool execution time
    tool_result = f"Found 5 results for {query}"
    tool_time = tracker.end_timer("tool_usage", request_id)
    
    # 3. LLM Generation Phase
    tracker.start_timer("llm_generation", request_id)
    # In real usage, this would be: response = agent.chat(prompt)
    time.sleep(0.15)  # Simulate LLM response time
    response = f"Based on my search, here's information about {query}..."
    llm_time = tracker.end_timer("llm_generation", request_id)
    
    # Get metrics
    metrics = tracker.get_metrics(request_id)
    
    # Display results
    print(f"\nResponse: {response}")
    print(f"\nLatency Breakdown:")
    print(f"  Planning: {planning_time:.3f}s")
    print(f"  Tool Usage: {tool_time:.3f}s")
    print(f"  LLM Generation: {llm_time:.3f}s")
    print(f"  Total: {planning_time + tool_time + llm_time:.3f}s")
    
    return response, metrics


if __name__ == "__main__":
    # Simulate multiple MCP requests
    queries = [
        "Python async programming",
        "Machine learning basics",
        "Docker best practices"
    ]
    
    for i, query in enumerate(queries):
        handle_mcp_request(query, f"mcp_request_{i}")
    
    # Show summary
    print("\n" + "="*50)
    print("OVERALL LATENCY SUMMARY")
    print("="*50)
    
    summary = tracker.get_summary()
    for request_id, phases in summary.items():
        print(f"\n{request_id}:")
        total = sum(phase_data['total'] for phase_data in phases.values())
        for phase, data in phases.items():
            percentage = (data['total'] / total) * 100
            print(f"  {phase}: {data['total']:.3f}s ({percentage:.1f}%)")