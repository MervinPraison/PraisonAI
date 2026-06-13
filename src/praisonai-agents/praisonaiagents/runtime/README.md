# Runtime System Documentation

This module provides runtime execution abstractions and protocols for standardizing agent execution across different harness types.

## Components

### 1. Agent Runtime System

The runtime system provides a pluggable abstraction layer for agent execution, allowing agents to run through different runtime implementations while maintaining a consistent interface.

#### Overview

The runtime system consists of:

- **AgentRuntimeProtocol**: Core protocol defining the runtime interface
- **RuntimeRegistry**: Plugin registry for runtime discovery and management  
- **Built-in PraisonAI Runtime**: Default embedded runtime wrapping existing agent logic
- **Entry Points**: Support for plugin runtime registration

#### Architecture

Following AGENTS.md protocol-driven design:

- **Core protocols only** in `praisonaiagents/runtime/`
- **Lightweight abstractions** with minimal dependencies
- **Async-first** design with proper typing
- **Plugin registry** for extensibility

#### Usage

##### Basic Runtime Resolution

```python
from praisonaiagents.runtime import resolve_runtime

# Get the built-in runtime
runtime = resolve_runtime("praisonai")

# Execute a turn
result = await runtime.run_turn("Hello world")
print(result.content)
```

##### Streaming Execution

```python
# Stream response deltas
async for delta in runtime.stream_turn("Tell me a story"):
    if delta.type == "text":
        print(delta.content, end="")
```

##### Runtime Registration

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

##### Plugin Runtime (Entry Points)

Add to your package's `pyproject.toml`:

```toml
[project.entry-points."praisonai.runtimes"]
my-runtime = "my_package.runtime:MyRuntimeClass"
```

#### Built-in Runtime

The `praisonai` runtime is the default built-in runtime that wraps the existing agent ChatMixin and execution logic. It:

- Supports all models that the LLM subsystem supports
- Delegates to existing Agent execution paths
- Provides backward compatibility
- Handles streaming and non-streaming execution

#### Protocol Compliance

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

#### Registry API

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

#### Error Handling

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

### 2. Runtime Tool Result Middleware

This module provides runtime-scoped tool result middleware for plugin harnesses. Plugin harnesses return tool results in vendor-specific shapes, and this middleware normalizes them before they reach hooks and memory adapters.

#### Overview

The middleware system follows the protocol-driven design of PraisonAI Agents:

- **Core Protocol**: `RuntimeToolResultMiddleware` - defines the normalization interface
- **Standardized Format**: `NormalizedToolResult` - consistent result format for downstream consumers
- **Registry**: `RuntimeRegistry` - manages per-runtime middleware instances
- **Zero Overhead**: Native `praisonai` runtime bypasses middleware to avoid allocation

#### Architecture

```
Tool Execution Flow:
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Plugin Harness  │───▶│ Runtime         │───▶│ Global Hooks    │───▶│ Memory          │
│ (vendor result) │    │ Middleware      │    │ (normalized)    │    │ Persistence     │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │ NormalizedTool  │
                    │ Result          │
                    └─────────────────┘
```

#### For Plugin Authors

##### 1. Implement the Middleware Protocol

```python
from praisonaiagents.runtime import RuntimeToolResultMiddleware, NormalizedToolResult, MiddlewareContext

class MyHarnessMiddleware:
    @property
    def runtime_id(self) -> str:
        return "my_plugin_harness"
    
    def normalize(self, result: Any, tool_name: str, ctx: MiddlewareContext) -> NormalizedToolResult:
        # Convert your vendor-specific result to standard format
        if isinstance(result, MyVendorResult):
            return NormalizedToolResult(
                content=result.data,
                success=result.status == "ok",
                error_message=result.error_msg if result.status != "ok" else None,
                metadata={
                    "vendor": "my_vendor",
                    "tool_version": result.version,
                    "execution_id": result.exec_id
                },
                execution_time_ms=ctx.execution_time_ms,
                raw_result=result  # For debugging/advanced use cases
            )
        
        # Fallback for unknown result types
        return NormalizedToolResult(content=result)
```

##### 2. Register Your Middleware

```python
from praisonaiagents.runtime import register_middleware

# During plugin initialization
middleware = MyHarnessMiddleware()
register_middleware("my_plugin_harness", middleware)
```

##### 3. Set Runtime ID on Agent

```python
from praisonaiagents import Agent

# Your plugin harness should set the runtime_id on agents it creates
agent = Agent(name="MyAgent", tools=[...])
agent._runtime_id = "my_plugin_harness"  # This triggers middleware lookup
```

#### Standard Result Format

The `NormalizedToolResult` provides a consistent interface for downstream consumers:

```python
@dataclass
class NormalizedToolResult:
    # Core result data
    content: Any  # The actual tool result (can be any type)
    
    # Standardized metadata
    success: bool = True
    error_message: Optional[str] = None
    
    # Rich metadata for downstream consumers
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Execution context
    execution_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    
    # Original raw result for debugging/advanced use cases
    raw_result: Optional[Any] = None
```

#### Common Patterns

##### Error Handling

```python
def normalize(self, result, tool_name, ctx):
    if isinstance(result, MyErrorResult):
        return NormalizedToolResult(
            content=None,
            success=False,
            error_message=result.error_description,
            metadata={
                "error_code": result.code,
                "error_category": result.category,
                "retryable": result.is_retryable
            },
            raw_result=result
        )
```

##### Rich Metadata

```python
def normalize(self, result, tool_name, ctx):
    return NormalizedToolResult(
        content=result.data,
        success=True,
        metadata={
            # Vendor identification
            "vendor": "my_vendor",
            "vendor_version": "2.1.0",
            
            # Execution metadata
            "tool_version": result.tool_version,
            "execution_id": result.exec_id,
            "cache_hit": result.from_cache,
            
            # Performance metadata
            "network_time_ms": result.network_latency,
            "processing_time_ms": result.processing_time,
            
            # Context metadata
            "region": result.execution_region,
            "model": result.model_used if hasattr(result, 'model_used') else None
        },
        raw_result=result
    )
```

##### Conditional Normalization

```python
def normalize(self, result, tool_name, ctx):
    # Different handling based on tool type
    if tool_name.startswith("search_"):
        return self._normalize_search_result(result, ctx)
    elif tool_name.startswith("db_"):
        return self._normalize_db_result(result, ctx)
    else:
        return self._normalize_generic_result(result, ctx)
```

#### Performance Considerations

- **Native Runtime**: The `praisonai` runtime bypasses middleware entirely to avoid allocation overhead
- **Lazy Loading**: Middleware modules use lazy loading to minimize startup time
- **Error Isolation**: Middleware failures don't break tool execution - they log warnings and continue
- **Thread Safety**: The registry is thread-safe for concurrent agent execution

## Testing

The runtime system includes comprehensive tests:

- Protocol compliance tests
- Registry functionality tests  
- Built-in runtime tests
- Integration tests
- Middleware tests

Run tests with:

```bash
pytest praisonaiagents/runtime/tests/
```

Use the provided test utilities to verify your middleware:

```python
from praisonaiagents.runtime.middleware import MiddlewareContext

def test_my_middleware():
    middleware = MyHarnessMiddleware()
    
    ctx = MiddlewareContext(
        tool_name="test_tool",
        runtime_id="my_plugin_harness",
        agent_id="test_agent",
        execution_time_ms=100.0
    )
    
    result = MyVendorResult(status="ok", data="test")
    normalized = middleware.normalize(result, "test_tool", ctx)
    
    assert normalized.success is True
    assert normalized.content == "test"
    assert normalized.metadata["vendor"] == "my_vendor"
```

## Registry Management

The registry supports runtime management for testing and plugin lifecycle:

```python
from praisonaiagents.runtime import get_default_registry

registry = get_default_registry()

# List registered runtimes
runtimes = registry.list_runtimes()

# Check if middleware is registered
if registry.has_middleware("my_runtime"):
    middleware = registry.get_middleware("my_runtime")

# Unregister for cleanup
registry.unregister("my_runtime")
```

## Future Extensions

The runtime system is designed to support:

- CLI backend migration to runtime abstraction
- Model-scoped runtime selection policies
- Turn-time runtime resolution for handoffs
- Runtime capability matrix and hook compatibility
- Prepared turn contexts with runtime plans