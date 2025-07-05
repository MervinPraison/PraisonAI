# MCP HTTP-Streaming Support

PraisonAI now supports HTTP-Streaming transport for Model Context Protocol (MCP) servers, in addition to the existing SSE (Server-Sent Events) transport. This enhancement provides better compatibility with the updated MCP standard while maintaining full backward compatibility.

## Features

- **HTTP-Streaming Transport**: Support for the new HTTP chunked streaming protocol
- **Auto-Detection**: Automatically selects the appropriate transport based on URL patterns
- **Backward Compatible**: All existing code continues to work without modifications
- **Minimal API Changes**: Only adds an optional `transport` parameter
- **Unified Interface**: Same API for both SSE and HTTP-Streaming transports

## Usage

### Python

#### Auto-Detection (Recommended)

```python
from praisonaiagents import Agent
from praisonaiagents.mcp import MCP

# URLs ending with /sse use SSE transport
agent = Agent(
    tools=MCP("http://localhost:8080/sse")  # Auto-detects SSE
)

# Other HTTP URLs use HTTP-Streaming transport
agent = Agent(
    tools=MCP("http://localhost:8080/stream")  # Auto-detects HTTP-Streaming
)
```

#### Explicit Transport Selection

```python
# Force specific transport
agent = Agent(
    tools=MCP("http://localhost:8080/api", transport="http-streaming")
)

# Available transports: "auto", "sse", "http-streaming", "stdio"
```

### TypeScript

#### Auto-Detection

```typescript
import { MCP } from 'praisonai/tools/mcp';

// Auto-detect transport based on URL
const mcp = new MCP('http://localhost:8080/stream');
await mcp.initialize();
```

#### Explicit Transport Selection

```typescript
// Force specific transport
const mcp = new MCP('http://localhost:8080/api', {
  transport: 'http-streaming',
  debug: true
});
await mcp.initialize();
```

## Transport Selection Logic

When `transport="auto"` (default):
- URLs ending with `/sse` → SSE transport
- Other HTTP URLs → HTTP-Streaming transport
- Local commands → Stdio transport

## API Reference

### Python

```python
MCP(
    command_or_string: str,
    args: Optional[List[str]] = None,
    transport: str = "auto",  # New parameter
    timeout: int = 60,
    debug: bool = False,
    **kwargs
)
```

### TypeScript

```typescript
new MCP(
    url: string,
    options?: {
        transport?: 'auto' | 'sse' | 'http-streaming';
        debug?: boolean;
    }
)
```

## Implementation Details

### HTTP-Streaming Protocol

The HTTP-Streaming transport implements:
- Chunked transfer encoding for streaming responses
- JSON-RPC message framing with newline delimiters
- Proper request/response correlation using message IDs
- Error handling and timeout support

### Architecture

```
MCP Class
├── Auto-detection logic
├── SSE Transport (existing)
│   └── SSEMCPClient
└── HTTP-Streaming Transport (new)
    └── HTTPStreamingMCPClient
```

## Migration Guide

**No migration needed!** All existing code continues to work:

```python
# This still works exactly as before
agent = Agent(
    tools=MCP("http://localhost:8080/sse")
)

# So does this
agent = Agent(
    tools=MCP("python /path/to/server.py")
)
```

## Examples

See the complete examples:
- Python: `src/praisonai-agents/examples/mcp_http_streaming_example.py`
- TypeScript: `src/praisonai-ts/examples/tools/mcp-http-streaming.ts`

## Testing

Run the backward compatibility test:

```bash
cd src/praisonai-agents
python tests/test_mcp_backward_compatibility.py
```

## Compatibility

- Requires MCP SDK version compatible with HTTP-Streaming
- Works with all existing MCP servers (SSE or HTTP-Streaming)
- Python 3.8+ and Node.js 16+ supported