"""
MCP Server with Latency Tracking Example

This shows how to add latency tracking to an MCP server
without modifying PraisonAI core files.
"""

from praisonaiagents import Agent, PraisonAIAgents
from praisonaiagents.mcp import HostedMCPServer
from latency_tracker_tool import tracker, get_latency_metrics
import json


class LatencyTrackedMCPServer(HostedMCPServer):
    """MCP Server with built-in latency tracking."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Import and use the original agents, not wrapped ones
        self._original_handle_request = self.handle_request
        self.handle_request = self._tracked_handle_request
    
    def _tracked_handle_request(self, request_data):
        """Wrapped request handler with latency tracking."""
        request_id = request_data.get('id', 'mcp_request')
        
        # Track the entire request
        with tracker.track("mcp_total_request", request_id):
            # Call original handler
            response = self._original_handle_request(request_data)
        
        # Add latency metrics to response if requested
        if request_data.get('include_latency_metrics', False):
            metrics = get_latency_metrics(request_id)
            response['latency_metrics'] = metrics
        
        return response


def create_mcp_agent_with_tracking(request_id: str = "mcp_request"):
    """Create an agent that tracks its operations."""
    
    class TrackedOperationAgent(Agent):
        """Agent that tracks planning, tool usage, and LLM calls."""
        
        def chat(self, *args, **kwargs):
            with tracker.track("planning", request_id):
                return super().chat(*args, **kwargs)
        
        def execute_tool(self, *args, **kwargs):
            with tracker.track("tool_usage", request_id):
                return super().execute_tool(*args, **kwargs)
    
    # Create the tracked agent
    agent = TrackedOperationAgent(
        name="MCPAssistant",
        role="MCP Request Handler",
        goal="Handle MCP requests with latency tracking",
        llm="gpt-4o-mini"
    )
    
    return agent


# Example usage for MCP server operators
def example_mcp_with_tracking():
    """Example showing how to use latency tracking with MCP server."""
    
    print("=== MCP Server Latency Tracking Example ===\n")
    
    # Simulate handling an MCP request
    request_id = "mcp_example_1"
    
    # Create tracked agent
    agent = create_mcp_agent_with_tracking(request_id)
    
    # Simulate the three phases mentioned in the issue
    print("1. Planning Phase:")
    with tracker.track("planning", request_id):
        planning_result = agent.chat("Plan how to search for Python async documentation")
    print(f"   Plan: {planning_result[:100]}...")
    
    print("\n2. Tool Usage Phase:")
    # If you have actual tools, they would be executed here
    with tracker.track("tool_usage", request_id):
        # Simulate tool execution
        import time
        time.sleep(0.1)  # Simulate tool delay
        tool_result = "Found 10 documentation pages about Python async"
    print(f"   Tool result: {tool_result}")
    
    print("\n3. LLM Answer Generation Phase:")
    with tracker.track("llm_generation", request_id):
        final_answer = agent.chat(f"Based on finding that {tool_result}, provide a concise summary")
    print(f"   Answer: {final_answer[:100]}...")
    
    # Get and display metrics
    print("\n=== Latency Metrics ===")
    metrics = get_latency_metrics(request_id)
    
    for phase, data in metrics.items():
        print(f"{phase}:")
        print(f"  - Total time: {data['total']:.3f}s")
        print(f"  - Count: {data['count']}")
        print(f"  - Average: {data['average']:.3f}s")
    
    # Calculate total time
    total_time = sum(data['total'] for data in metrics.values())
    print(f"\nTotal execution time: {total_time:.3f}s")
    
    # Show percentage breakdown
    print("\nTime breakdown:")
    for phase, data in metrics.items():
        percentage = (data['total'] / total_time) * 100
        print(f"  - {phase}: {percentage:.1f}%")


# Function to wrap existing MCP server with tracking
def add_tracking_to_mcp_server(mcp_server):
    """Add latency tracking to an existing MCP server instance."""
    
    original_handle = mcp_server.handle_request
    
    def tracked_handle(request_data):
        request_id = request_data.get('id', 'mcp_request')
        
        with tracker.track("mcp_request_total", request_id):
            # You can add more granular tracking here based on request type
            request_type = request_data.get('method', 'unknown')
            
            with tracker.track(f"mcp_{request_type}", request_id):
                response = original_handle(request_data)
        
        return response
    
    mcp_server.handle_request = tracked_handle
    return mcp_server


# Utility function for MCP server monitoring
def get_mcp_latency_summary():
    """Get a formatted summary of MCP server latency."""
    
    summary = tracker.get_summary()
    
    if not summary:
        return "No MCP requests tracked yet."
    
    report = "MCP Server Latency Summary\n"
    report += "=" * 50 + "\n"
    
    for request_id, metrics in summary.items():
        if request_id.startswith("mcp_"):
            report += f"\nRequest: {request_id}\n"
            
            total_time = 0
            for phase, data in metrics.items():
                phase_time = data['total']
                total_time += phase_time
                report += f"  {phase}: {phase_time:.3f}s\n"
            
            report += f"  Total: {total_time:.3f}s\n"
    
    return report


if __name__ == "__main__":
    # Run the example
    example_mcp_with_tracking()
    
    # Show overall summary
    print("\n" + "=" * 50)
    print(get_mcp_latency_summary())