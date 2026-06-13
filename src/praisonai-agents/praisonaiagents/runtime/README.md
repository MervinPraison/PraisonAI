# Agent Runtime System

The runtime system provides a pluggable abstraction layer for agent execution, allowing agents to run through different runtime implementations while maintaining a consistent interface.

## Overview

The runtime system consists of:

- **AgentRuntimeProtocol**: Core protocol defining the runtime interface
- **RuntimeRegistry**: Plugin registry for runtime discovery and management  
- **Built-in PraisonAI Runtime**: Default embedded runtime wrapping existing agent logic
- **Entry Points**: Support for plugin runtime registration

## Architecture

Following AGENTS.md protocol-driven design:

- **Core protocols only** in `praisonaiagents/runtime/`
- **Lightweight abstractions** with minimal dependencies
- **Async-first** design with proper typing
- **Plugin registry** for extensibility

## Usage

### Basic Runtime Resolution

```python
from praisonaiagents.runtime import resolve_runtime

# Get the built-in runtime
runtime = resolve_runtime("praisonai")

# Execute a turn
result = await runtime.run_turn("Hello world")
print(result.content)
```

### Streaming Execution

```python
# Stream response deltas
async for delta in runtime.stream_turn("Tell me a story"):
    if delta.type == "text":
        print(delta.content, end="")
```

### Runtime Registration

```python
from praisonaiagents.runtime import register_runtime

class MyCustomRuntime:
    def supports(self, model_ref=None):
        return True
    
    async def run_turn(self, prompt, **kwargs):
        # Custom implementation
        return RuntimeResult(content="Custom response")
    
    async def stream_turn(self, prompt, **kwargs):
        yield RuntimeDelta(type="text", content="Streaming...")

# Register runtime
register_runtime("my-runtime", lambda: MyCustomRuntime())
```

### Plugin Runtime (Entry Points)

Add to your package's `pyproject.toml`:

```toml
[project.entry-points."praisonai.runtimes"]
my-runtime = "my_package.runtime:MyRuntimeClass"
```

## Built-in Runtime

The `praisonai` runtime is the default built-in runtime that wraps the existing agent ChatMixin and execution logic. It:

- Supports all models that the LLM subsystem supports
- Delegates to existing Agent execution paths
- Provides backward compatibility
- Handles streaming and non-streaming execution

## Protocol Compliance

All runtimes must implement `AgentRuntimeProtocol`:

```python
class MyRuntime:
    def supports(self, model_ref: Optional[str] = None) -> bool:
        """Check if runtime supports the model."""
        ...
    
    async def run_turn(
        self, 
        prompt: str, 
        *,
        system_prompt: Optional[str] = None,
        model_ref: Optional[str] = None,
        **kwargs
    ) -> RuntimeResult:
        """Execute a single turn."""
        ...
    
    async def stream_turn(
        self, 
        prompt: str, 
        **kwargs
    ) -> AsyncIterator[RuntimeDelta]:
        """Stream response deltas."""
        ...
```

## Registry API

The runtime registry provides thread-safe registration and resolution:

```python
from praisonaiagents.runtime import (
    register_runtime,
    list_runtimes, 
    resolve_runtime,
    is_runtime_available
)

# List available runtimes
runtimes = list_runtimes()

# Check availability
if is_runtime_available("my-runtime"):
    runtime = resolve_runtime("my-runtime")
```

## Error Handling

Runtimes should handle errors gracefully and return `RuntimeResult` objects with error information rather than raising exceptions:

```python
try:
    # Runtime execution logic
    result = await some_operation()
    return RuntimeResult(content=result, metadata={"success": True})
except Exception as e:
    return RuntimeResult(
        content="", 
        error=str(e),
        metadata={"success": False}
    )
```

## Testing

The runtime system includes comprehensive tests:

- Protocol compliance tests
- Registry functionality tests  
- Built-in runtime tests
- Integration tests

Run tests with:

```bash
pytest praisonaiagents/runtime/tests/
```

## Future Extensions

The runtime system is designed to support:

- CLI backend migration to runtime abstraction
- Model-scoped runtime selection policies
- Turn-time runtime resolution for handoffs
- Runtime capability matrix and hook compatibility
- Prepared turn contexts with runtime plans