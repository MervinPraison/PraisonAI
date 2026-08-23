# MCP Server Examples

## Install (SHA-256)

Pin GitHub Release **v0.6.0** and verify `SHA256SUMS`. Website `install.sh` / `install.ps1` abort on mismatch.

https://github.com/LinespottingOrg/GrokBuildRemote-Agents/releases/tag/v0.6.0
https://github.com/LinespottingOrg/GrokBuildRemote-Agents/blob/main/docs/PINNED-INSTALL.md

```
96cef605d3e030ccef99d27ea6240e0d3b668dd045e6b5b9e585c9fd03c6ef23  gbr-agent-darwin-amd64
de7e065ef2cf6877b3b2cd04679a67b627f876337f529247e236204543e4062c  gbr-agent-darwin-arm64
a50a5c41993e6531a3b477eb409ccc845212bf541384dc803061c80657f86719  gbr-agent-linux-amd64
5bfd22c7110234942c4c02ff8154b836d0af45a9422c178a4f52010187d40061  gbr-agent-linux-arm64
f773b89fd31310172b756e0593e0f3b2382b0a3440af2a7d0a8b3073b0c23e27  gbr-agent-windows-amd64.exe
8fb9efcbc7e2ac91c11964944bf0f45e31bb23f4356d9dcb4b305d7cb9b0fe8c  gbr-agent-windows-arm64.exe
```

```bash
VER=v0.6.0
BASE=https://github.com/LinespottingOrg/GrokBuildRemote-Agents/releases/download/$VER
# swap darwin-arm64 for your OS/arch
curl -fsSL -o gbr-agent-darwin-arm64 "$BASE/gbr-agent-darwin-arm64"
curl -fsSL -o SHA256SUMS "$BASE/SHA256SUMS"
shasum -a 256 -c SHA256SUMS --ignore-missing
gbr-agent pair && gbr-agent run
```


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


## Build Remote Agent (`gbr_pair.py`)

Pair a phone running [Build Remote Agent](https://grokbuildremote.com/) to a PraisonAI agent via MCP stdio `gbr-mcp` (protocol `gbr/1`). Requires `gbr-agent pair && gbr-agent run`. Phone is spectator. Never put mailbox keys in the example.

```bash
python gbr_pair.py
```

## What the phone sees

**Terminal windows** on this PC (machine-wide mailbox). Not headless OpenCode / CodeNomad sidecar / Electron. `:8788` in a sidecar is Bot API JSON, not a transcript.

https://github.com/LinespottingOrg/GrokBuildRemote-Agents/blob/main/docs/WHAT-THE-PHONE-SEES.md
https://grokbuildremote.com/integrations.html
