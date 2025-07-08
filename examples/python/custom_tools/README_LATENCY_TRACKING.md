# Minimal Latency Tracking for PraisonAI MCP Server

This solution provides latency tracking for MCP servers without modifying any PraisonAI core files. It's implemented as a custom tool that can be used externally.

## Overview

The latency tracking solution measures three key phases:
1. **Planning Process** - Time taken for agent planning and decision making
2. **Tool Usage** - Time spent executing tools
3. **LLM Answer Generation** - Time spent generating responses

## Quick Start

### Option 1: Use as a Custom Tool

```python
from latency_tracker_tool import latency_tracking_tool

# Add to your agent
agent = Agent(
    name="Assistant",
    role="Helper",
    tools=[latency_tracking_tool]
)

# Track manually
latency_tracking_tool("start", "planning", "request_1")
response = agent.chat("Your query")
latency_tracking_tool("end", "planning", "request_1")

# Get metrics
metrics = latency_tracking_tool("metrics", request_id="request_1")
```

### Option 2: Use Context Managers

```python
from latency_tracker_tool import tracker

# Track with context manager
with tracker.track("planning", "request_1"):
    response = agent.chat("Your query")

# Get metrics
metrics = tracker.get_metrics("request_1")
```

### Option 3: Use Wrapper Classes

```python
from latency_tracker_tool import create_tracked_agent

# Create tracked agent class
TrackedAgent = create_tracked_agent(Agent)

# Use like normal agent
agent = TrackedAgent(
    name="Assistant",
    role="Helper",
    request_id="request_1"
)

# Operations are automatically tracked
response = agent.chat("Your query")
```

## MCP Server Integration

### Basic MCP Tracking

```python
from latency_tracker_tool import tracker

def handle_mcp_request(request_data):
    request_id = request_data.get('id', 'default')
    
    with tracker.track("total_request", request_id):
        # Track planning
        with tracker.track("planning", request_id):
            plan = create_plan(request_data)
        
        # Track tool usage
        with tracker.track("tool_usage", request_id):
            tool_results = execute_tools(plan)
        
        # Track LLM generation
        with tracker.track("llm_generation", request_id):
            response = generate_response(tool_results)
    
    # Include metrics in response
    metrics = tracker.get_metrics(request_id)
    return {
        "response": response,
        "latency_metrics": metrics
    }
```

### Advanced MCP Server Wrapper

```python
from latency_tracker_tool import tracker

def add_tracking_to_mcp_server(mcp_server):
    """Add tracking to existing MCP server."""
    original_handle = mcp_server.handle_request
    
    def tracked_handle(request_data):
        request_id = request_data.get('id', 'mcp_request')
        
        with tracker.track("mcp_total", request_id):
            response = original_handle(request_data)
        
        return response
    
    mcp_server.handle_request = tracked_handle
    return mcp_server
```

## Tools with Built-in Tracking

Create a `tools.py` file in your project root:

```python
from latency_tracker_tool import track_latency, tracker

@track_latency("tool_search", "current_request")
def search_tool(query: str) -> str:
    """Search with automatic latency tracking."""
    # Your search logic
    return results

def get_latency_report(request_id: str = "current_request") -> str:
    """Get latency metrics as a tool."""
    metrics = tracker.get_metrics(request_id)
    # Format and return report
    return formatted_report
```

## API Reference

### LatencyTracker Class

- `start_timer(phase, request_id)` - Start timing a phase
- `end_timer(phase, request_id)` - End timing and return elapsed time
- `track(phase, request_id)` - Context manager for tracking
- `get_metrics(request_id)` - Get metrics for a request
- `get_summary()` - Get summary of all requests
- `clear(request_id)` - Clear tracking data

### Metrics Format

```json
{
  "planning": {
    "count": 1,
    "total": 1.234,
    "average": 1.234,
    "min": 1.234,
    "max": 1.234,
    "latest": 1.234
  },
  "tool_usage": {
    "count": 3,
    "total": 0.567,
    "average": 0.189,
    "min": 0.150,
    "max": 0.250,
    "latest": 0.167
  }
}
```

## Examples

See the following example files:
- `example_latency_tracking.py` - Basic usage examples
- `mcp_server_latency_example.py` - MCP server integration
- `tools_with_latency.py` - Tools with built-in tracking

## Benefits

1. **No Core Modifications** - Works without changing PraisonAI source code
2. **Flexible** - Multiple ways to integrate (tool, decorator, wrapper, context manager)
3. **Thread-Safe** - Supports concurrent requests
4. **Minimal Overhead** - Lightweight tracking with negligible performance impact
5. **Extensible** - Easy to add custom phases and metrics

## Use Cases

1. **Performance Monitoring** - Track and optimize MCP server performance
2. **Debugging** - Identify bottlenecks in request processing
3. **SLA Monitoring** - Ensure response times meet requirements
4. **Capacity Planning** - Understand resource usage patterns
5. **A/B Testing** - Compare performance of different implementations

## Tips

1. Use unique request IDs for concurrent request tracking
2. Clear old tracking data periodically to free memory
3. Add tracking to critical paths only to minimize overhead
4. Use phase names consistently across your application
5. Consider logging metrics for long-term analysis

## Integration with Existing Monitoring

The metrics can be easily exported to monitoring systems:

```python
# Export to Prometheus
def export_to_prometheus():
    summary = tracker.get_summary()
    # Convert to Prometheus format
    
# Export to CloudWatch
def export_to_cloudwatch():
    metrics = tracker.get_metrics()
    # Send to CloudWatch

# Export to custom logging
import json
import logging

def log_metrics(request_id):
    metrics = tracker.get_metrics(request_id)
    logging.info(f"Latency metrics: {json.dumps(metrics)}")
```