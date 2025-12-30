# MCP Server Examples

Examples demonstrating the MCP Server v2 features per MCP Protocol Version 2025-11-25.

## Features Demonstrated

### 1. Pagination (`pagination_example.py`)

Demonstrates pagination for `tools/list`, `resources/list`, and `prompts/list`:

- Opaque cursor encoding (base64url)
- Server-determined page size (default: 50, max: 100)
- `nextCursor` for fetching more results
- Cursor validation with JSON-RPC errors

```bash
python pagination_example.py
```

### 2. Tool Annotations (`tool_annotations_example.py`)

Demonstrates MCP 2025-11-25 tool annotation hints:

- `readOnlyHint`: Tool only reads data
- `destructiveHint`: Tool may have destructive effects
- `idempotentHint`: Safe to call multiple times
- `openWorldHint`: Interacts with external world

```bash
python tool_annotations_example.py
```

### 3. CLI Tools (`cli_tools_example.sh`)

Demonstrates the new CLI commands:

```bash
# List tools with pagination
praisonai mcp list-tools --limit 10
praisonai mcp list-tools --cursor <cursor> --json

# Search tools
praisonai mcp tools search "query"
praisonai mcp tools search --category memory
praisonai mcp tools search --read-only
praisonai mcp tools search --json

# Get tool info
praisonai mcp tools info <tool-name>
praisonai mcp tools info <tool-name> --json

# Get tool schema
praisonai mcp tools schema <tool-name>
```

## API Reference

### Pagination

```python
from praisonai.mcp_server.registry import MCPToolRegistry

registry = MCPToolRegistry()
# ... register tools ...

# Get first page
tools, next_cursor = registry.list_paginated(page_size=50)

# Get next page
if next_cursor:
    more_tools, next_cursor = registry.list_paginated(cursor=next_cursor)
```

### Tool Search

```python
# Search by query
tools, next_cursor, total = registry.search(query="memory")

# Filter by category
tools, _, _ = registry.search(category="file")

# Filter by read-only hint
tools, _, _ = registry.search(read_only=True)

# Combined filters with pagination
tools, next_cursor, total = registry.search(
    query="data",
    category="storage",
    read_only=True,
    page_size=10,
)
```

### Tool Annotations

```python
from praisonai.mcp_server.registry import MCPToolDefinition

# Read-only tool
tool = MCPToolDefinition(
    name="data.read",
    description="Read data",
    handler=read_handler,
    input_schema={"type": "object"},
    read_only_hint=True,
    destructive_hint=False,
)

# Destructive tool
tool = MCPToolDefinition(
    name="file.delete",
    description="Delete file",
    handler=delete_handler,
    input_schema={"type": "object"},
    destructive_hint=True,
    idempotent_hint=False,
)
```

## MCP Protocol Compliance

These examples comply with MCP Protocol Version 2025-11-25:

- Pagination uses opaque cursors (base64url encoded)
- Server determines page size (client cannot override)
- Invalid cursors return JSON-RPC error code -32602
- Tool annotations follow the spec defaults:
  - `readOnlyHint`: false
  - `destructiveHint`: true
  - `idempotentHint`: false
  - `openWorldHint`: true
