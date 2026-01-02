# Profiling Module

PraisonAI provides a unified profiling module for programmatic performance analysis.

## Quick Start

```python
from praisonai.cli.execution import (
    ExecutionRequest,
    Profiler,
    ProfilerConfig,
)

# Create execution request
request = ExecutionRequest(prompt="What is 2+2?")

# Configure profiler
config = ProfilerConfig(layer=1)

# Run with profiling
profiler = Profiler(config)
result, report = profiler.profile_sync(request)

# Access results
print(f"Output: {result.output}")
print(f"Total time: {report.timing.total_ms}ms")
```

## ExecutionRequest

Immutable request descriptor for execution.

```python
from praisonai.cli.execution import ExecutionRequest

# Basic request
request = ExecutionRequest(prompt="Hello")

# With model
request = ExecutionRequest(
    prompt="Hello",
    model="gpt-4",
    agent_name="MyAgent",
)

# With streaming
request = ExecutionRequest(
    prompt="Hello",
    stream=True,
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `prompt` | str | Required | The prompt to execute |
| `agent_name` | str | "Assistant" | Name of the agent |
| `agent_instructions` | str | None | Custom instructions |
| `model` | str | None | Model to use |
| `stream` | bool | False | Enable streaming |
| `tools` | tuple | () | Tools to provide |

## ProfilerConfig

Configuration for profiling behavior.

```python
from praisonai.cli.execution import ProfilerConfig

# Layer 0: Wall-clock only (< 1ms overhead)
config = ProfilerConfig(layer=0)

# Layer 1: + cProfile stats (~5% overhead)
config = ProfilerConfig(layer=1)

# Layer 2: + Call graph (~15% overhead)
config = ProfilerConfig(
    layer=2,
    show_callers=True,
    show_callees=True,
)

# From CLI flags
config = ProfilerConfig.from_flags(
    profile=True,
    deep=True,
    network=False,
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `layer` | int | 1 | Profiling layer (0, 1, or 2) |
| `limit` | int | 30 | Max functions to show |
| `sort_by` | str | "cumulative" | Sort by: cumulative, time, calls |
| `show_callers` | bool | False | Show caller functions |
| `show_callees` | bool | False | Show callee functions |
| `track_network` | bool | False | Track network requests |
| `output_format` | str | "text" | Output format: text, json |
| `save_path` | str | None | Path to save artifacts |

## Profiler

The main profiler class that wraps execution.

```python
from praisonai.cli.execution import Profiler, ProfilerConfig, ExecutionRequest

config = ProfilerConfig(layer=1)
profiler = Profiler(config)

request = ExecutionRequest(prompt="Hello")
result, report = profiler.profile_sync(request, invocation_method="api")
```

### Methods

#### `profile_sync(request, invocation_method="profile_command")`

Profile synchronous execution.

**Parameters:**
- `request`: ExecutionRequest - The execution request
- `invocation_method`: str - How this was invoked (for report)

**Returns:** Tuple of (ExecutionResult, ProfileReport)

## ProfileReport

The canonical profile report with timing and statistics.

```python
# Access timing breakdown
print(f"Total: {report.timing.total_ms}ms")
print(f"Imports: {report.timing.imports_ms}ms")
print(f"Agent Init: {report.timing.agent_init_ms}ms")
print(f"Execution: {report.timing.execution_ms}ms")

# Access function stats (layer 1+)
if report.functions:
    for func in report.functions[:5]:
        print(f"{func.name}: {func.cumulative_time_ms}ms")

# Access call graph (layer 2)
if report.call_graph:
    print(f"Edges: {len(report.call_graph.edges)}")

# Export formats
json_str = report.to_json()
text_str = report.to_text()
dict_data = report.to_dict()
```

### Schema Version

The report uses schema version `1.0`. Schema is frozen after release - new fields are always optional with defaults.

### Mandatory Fields

- `schema_version`: str
- `run_id`: str
- `timestamp`: str (ISO 8601)
- `invocation`: InvocationInfo
- `timing`: TimingBreakdown
- `response_preview`: str

### Optional Fields

- `functions`: List[FunctionStat] (layer 1+)
- `call_graph`: CallGraph (layer 2)
- `network`: List[RequestTiming] (if track_network)

## ExecutionResult

Result of execution with output and metadata.

```python
# Access output
print(result.output)
print(result.success)
print(result.run_id)

# Check for errors
if result.error:
    print(f"Error: {result.error}")

# Duration
print(f"Duration: {result.duration_ms}ms")
```

## Data Bounds

Profile data is strictly bounded to prevent memory issues:

| Data Type | Maximum |
|-----------|---------|
| Function stats | 1000 |
| Call graph edges | 5000 |
| Network requests | 100 |

## Example: Full Profiling Workflow

```python
from praisonai.cli.execution import (
    ExecutionRequest,
    Profiler,
    ProfilerConfig,
)

# Configure deep profiling
config = ProfilerConfig(
    layer=2,
    limit=50,
    show_callers=True,
    show_callees=True,
)

# Create request
request = ExecutionRequest(
    prompt="Explain quantum computing in simple terms",
    model="gpt-4",
)

# Profile execution
profiler = Profiler(config)
result, report = profiler.profile_sync(request)

# Print text report
print(report.to_text())

# Save JSON report
with open("profile.json", "w") as f:
    f.write(report.to_json())

# Analyze timing
print(f"\nTiming Analysis:")
print(f"  Import overhead: {report.timing.imports_ms / report.timing.total_ms * 100:.1f}%")
print(f"  Execution time: {report.timing.execution_ms / report.timing.total_ms * 100:.1f}%")

# Top 5 hotspots
if report.functions:
    print(f"\nTop 5 Hotspots:")
    for func in report.functions[:5]:
        print(f"  {func.name}: {func.cumulative_time_ms:.2f}ms ({func.calls} calls)")
```

## Invariants

The profiling module guarantees:

1. **Output Equivalence**: Profiled execution produces identical output to non-profiled execution
2. **Schema Stability**: Schema version 1.0 is frozen; new fields are always optional
3. **Bounded Data**: All profile data respects maximum bounds
4. **Zero Overhead When Disabled**: No profiling code runs unless explicitly enabled
