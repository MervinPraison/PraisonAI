# Runtime Tool Result Middleware

This module provides runtime-scoped tool result middleware for plugin harnesses. Plugin harnesses return tool results in vendor-specific shapes, and this middleware normalizes them before they reach hooks and memory adapters.

## Overview

The middleware system follows the protocol-driven design of PraisonAI Agents:

- **Core Protocol**: `RuntimeToolResultMiddleware` - defines the normalization interface
- **Standardized Format**: `NormalizedToolResult` - consistent result format for downstream consumers
- **Registry**: `RuntimeRegistry` - manages per-runtime middleware instances
- **Zero Overhead**: Native `praisonai` runtime bypasses middleware to avoid allocation

## Architecture

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

## For Plugin Authors

### 1. Implement the Middleware Protocol

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

### 2. Register Your Middleware

```python
from praisonaiagents.runtime import register_middleware

# During plugin initialization
middleware = MyHarnessMiddleware()
register_middleware("my_plugin_harness", middleware)
```

### 3. Set Runtime ID on Agent

```python
from praisonaiagents import Agent

# Your plugin harness should set the runtime_id on agents it creates
agent = Agent(name="MyAgent", tools=[...])
agent._runtime_id = "my_plugin_harness"  # This triggers middleware lookup
```

## Standard Result Format

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

## Common Patterns

### Error Handling

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

### Rich Metadata

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

### Conditional Normalization

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

## Performance Considerations

- **Native Runtime**: The `praisonai` runtime bypasses middleware entirely to avoid allocation overhead
- **Lazy Loading**: Middleware modules use lazy loading to minimize startup time
- **Error Isolation**: Middleware failures don't break tool execution - they log warnings and continue
- **Thread Safety**: The registry is thread-safe for concurrent agent execution

## Testing

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