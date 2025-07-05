# Latency Tracking for PraisonAI Agents

This module provides minimal latency tracking for MCP servers and agents to measure performance across different phases of execution.

## Features

- **Minimal code changes** - Integrated with just imports and context managers
- **Phase-based tracking** - Measures planning, tool usage, and LLM generation separately
- **Thread-safe** - Supports concurrent requests
- **Configurable** - Enable/disable via environment variable or programmatically
- **Zero overhead when disabled** - No performance impact when tracking is off

## Tracked Phases

1. **Planning Phase** (`planning`) - Time spent in `agent.chat()` processing prompts and deciding actions
2. **Tool Usage Phase** (`tool_usage`) - Time spent in `agent.execute_tool()` executing tools
3. **LLM Generation Phase** (`llm_generation`) - Time spent in `llm.get_response()` calling LLM APIs

## Usage

### Enable Tracking

```python
# Method 1: Environment variable
export PRAISON_LATENCY_TRACKING=true

# Method 2: Programmatically
from praisonaiagents.monitoring import enable_tracking
enable_tracking()
```

### Basic Usage

```python
from praisonaiagents import Agent
from praisonaiagents.monitoring import (
    enable_tracking,
    start_request,
    end_request,
    get_latency_summary
)

# Enable tracking
enable_tracking()

# Create agent
agent = Agent(name="MyAgent", instructions="...")

# Track a request
start_request("request_123")
response = agent.chat("What time is it?")
metrics = end_request()

# Print metrics
print(f"Total time: {metrics['total_time']:.3f}s")
for phase, data in metrics['phases'].items():
    print(f"{phase}: {data['total']:.3f}s")
```

### MCP Server Integration

For MCP servers, wrap the execute method:

```python
from praisonaiagents import Agent
from praisonaiagents.monitoring import start_request, end_request

agent = Agent(name="MCPAgent", instructions="...")

# In your MCP handler
async def handle_request(prompt):
    start_request(prompt[:50])
    try:
        result = await agent.achat(prompt)
        metrics = end_request()
        # Log or store metrics as needed
        return result
    except Exception as e:
        end_request()  # Clean up
        raise
```

### Get Summary Statistics

```python
summary = get_latency_summary()
for phase, stats in summary['phases'].items():
    print(f"{phase}: avg={stats['average_time']:.3f}s")
```

## API Reference

### Functions

- `enable_tracking()` - Enable latency tracking
- `disable_tracking()` - Disable latency tracking
- `is_tracking_enabled() -> bool` - Check if tracking is enabled
- `start_request(request_id: Optional[str])` - Start tracking a request
- `end_request() -> Dict[str, Any]` - End tracking and get metrics
- `get_latency_summary() -> Dict[str, Any]` - Get summary of all requests
- `track_phase(phase: str)` - Context manager for custom phase tracking
- `track_function(phase: str)` - Decorator for function tracking

### Context Manager

```python
from praisonaiagents.monitoring import track_phase

with track_phase("custom_phase"):
    # Your code here
    pass
```

### Decorator

```python
from praisonaiagents.monitoring import track_function

@track_function("data_processing")
def process_data(data):
    # Your code here
    return result
```

## Output Format

### Request Metrics
```json
{
  "request_id": "request_123",
  "total_time": 1.234,
  "phases": {
    "planning": {
      "total": 0.100,
      "count": 1,
      "average": 0.100,
      "times": [0.100]
    },
    "tool_usage": {
      "total": 0.500,
      "count": 2,
      "average": 0.250,
      "times": [0.300, 0.200]
    },
    "llm_generation": {
      "total": 0.634,
      "count": 1,
      "average": 0.634,
      "times": [0.634]
    }
  }
}
```

### Summary Statistics
```json
{
  "enabled": true,
  "phases": {
    "planning": {
      "total_requests": 10,
      "total_time": 2.5,
      "average_time": 0.25,
      "min_time": 0.1,
      "max_time": 0.5
    }
  }
}
```

## Performance Considerations

- Tracking adds minimal overhead (~microseconds per phase)
- When disabled, tracking functions become no-ops
- Thread-local storage prevents contention between requests
- Metrics are kept in memory - export periodically for long-running servers

## Examples

See the `examples/python/api/` directory for complete examples:
- `agent-latency-tracking.py` - Basic agent latency tracking
- `mcp-server-with-latency.py` - MCP server with latency reporting