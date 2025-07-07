# MCP HTTP-Streaming Support

This document describes the HTTP-Streaming transport implementation for MCP (Model Context Protocol) in PraisonAI.

## Overview

HTTP-Streaming provides bidirectional streaming communication over HTTP using chunked transfer encoding. This transport method offers advantages over SSE (Server-Sent Events) including:

- **Bidirectional streaming** - Both client and server can stream data
- **Binary support** - Can transmit binary data, not just text
- **Lower overhead** - More efficient than SSE's text-based protocol
- **Better performance** - Ideal for high-throughput scenarios

## Usage

### Auto-Detection (Default)

The MCP client automatically detects the appropriate transport based on URL patterns:

```python
# SSE transport (URLs ending with /sse)
agent = Agent(
    tools=MCP("http://localhost:8080/sse")  # Uses SSE
)

# HTTP-Streaming transport (other HTTP URLs)
agent = Agent(
    tools=MCP("http://localhost:8080/api")  # Uses HTTP-Streaming
)
```

### Explicit Transport Selection

You can explicitly specify the transport type:

```python
# Force SSE transport
agent = Agent(
    tools=MCP("http://localhost:8080/api", transport="sse")
)

# Force HTTP-Streaming transport
agent = Agent(
    tools=MCP("http://localhost:8080/sse", transport="http-streaming")
)
```

### TypeScript Usage

The TypeScript implementation follows the same pattern:

```typescript
import { MCP } from '@praisonai/agents/tools';

// Auto-detection
const mcpAuto = new MCP("http://localhost:8080/api");
await mcpAuto.initialize();

// Explicit transport
const mcpExplicit = new MCP("http://localhost:8080/api", {
  transport: "http-streaming",
  debug: true,
  headers: {
    "Authorization": "Bearer token"
  }
});
await mcpExplicit.initialize();
```

## Transport Detection Rules

The following URL patterns automatically use SSE transport:
- `/sse` (exact ending)
- `/sse/` (with trailing slash)
- `/events` (exact ending)
- `/stream` (exact ending)
- `/server-sent-events`
- URLs containing `transport=sse` query parameter

All other HTTP/HTTPS URLs default to HTTP-Streaming transport.

## Implementation Details

### Message Format

HTTP-Streaming uses NDJSON (Newline Delimited JSON) format:
- Each message is a complete JSON object
- Messages are separated by newline characters (`\n`)
- Supports efficient streaming parsing

### Python Architecture

```
MCP (main class)
├── _detect_transport() - Auto-detection logic
├── HTTPStreamingMCPClient - HTTP-Streaming implementation
│   ├── HTTPStreamingTransport - Low-level transport
│   ├── HTTPReadStream - Read adapter
│   └── HTTPWriteStream - Write adapter
└── SSEMCPClient - SSE implementation (existing)
```

### TypeScript Architecture

```
MCP (unified class)
├── detectTransport() - Auto-detection logic
├── MCPHttpStreaming - HTTP-Streaming implementation
│   └── HTTPStreamingTransport - Transport layer
│       ├── HTTPStreamingTransport - Modern browsers
│       └── HTTPStreamingTransportFallback - Legacy browsers
└── MCPSse - SSE implementation (existing)
```

## Server Implementation

### Python Server Example

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import json
import asyncio

app = FastAPI()

@app.post("/mcp/v1/stream")
async def mcp_stream(request: Request):
    async def generate():
        async for chunk in request.stream():
            # Process incoming messages
            message = json.loads(chunk)
            
            # Generate response
            response = process_mcp_message(message)
            yield json.dumps(response).encode() + b'\n'
    
    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson"
    )
```

### Node.js Server Example

```javascript
const express = require('express');
const app = express();

app.post('/mcp/v1/stream', (req, res) => {
  res.writeHead(200, {
    'Content-Type': 'application/x-ndjson',
    'Transfer-Encoding': 'chunked'
  });

  req.on('data', (chunk) => {
    const message = JSON.parse(chunk);
    const response = processMCPMessage(message);
    res.write(JSON.stringify(response) + '\n');
  });

  req.on('end', () => {
    res.end();
  });
});
```

## Configuration Options

### Python Options

```python
MCP(
    url,
    transport="http-streaming",  # Explicit transport
    timeout=60,                  # Request timeout in seconds
    debug=True,                  # Enable debug logging
    headers={                    # Custom headers
        "Authorization": "Bearer token"
    }
)
```

### TypeScript Options

```typescript
new MCP(url, {
  transport: "http-streaming",  // Explicit transport
  timeout: 60000,              // Timeout in milliseconds
  debug: true,                 // Enable debug logging
  headers: {                   // Custom headers
    "Authorization": "Bearer token"
  },
  fallbackMode: false          // Force fallback for testing
})
```

## Backward Compatibility

The implementation maintains 100% backward compatibility:

1. **Existing SSE URLs** continue to use SSE transport
2. **Stdio commands** work unchanged
3. **NPX commands** work unchanged
4. **All existing code** continues to function without modification

## Migration Guide

No migration is required! Existing code continues to work. To use HTTP-Streaming:

1. **Option 1**: Use URLs that don't match SSE patterns (recommended)
2. **Option 2**: Add `transport="http-streaming"` parameter

## Troubleshooting

### Debug Mode

Enable debug logging to see transport selection:

```python
MCP(url, debug=True)
```

### Common Issues

1. **Connection Refused**: Ensure the server supports HTTP-Streaming at the endpoint
2. **Transport Errors**: Check if the server implements the correct protocol
3. **Browser Compatibility**: TypeScript fallback mode handles older browsers

## Performance Considerations

HTTP-Streaming is recommended for:
- High-frequency message exchange
- Large message payloads
- Binary data transmission
- Bidirectional communication needs

SSE remains suitable for:
- Simple server-to-client streaming
- Text-only data
- Browser compatibility requirements
- Existing SSE infrastructure

## Future Enhancements

Potential future improvements:
- WebSocket transport option
- gRPC streaming support
- Connection pooling
- Automatic reconnection for HTTP-Streaming
- Compression support