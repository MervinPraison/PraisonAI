# PraisonAI MCP

Host PraisonAI agents and tools as an [MCP](https://modelcontextprotocol.io) server for Cursor, Claude Desktop, and other MCP clients.

## Install

```bash
pip install "praisonai-mcp[all]"

# Or via the umbrella product
pip install "praisonai[mcp]"
```

## Quickstart

```bash
export OPENAI_API_KEY=sk-...
# Standalone heavy host (full argparse options)
praisonai-mcp serve --transport stdio
praisonai-mcp list-tools
praisonai-mcp doctor

# Via umbrella CLI (same host commands on `praisonai mcp …`)
praisonai mcp serve --transport stdio
praisonai mcp list-tools
```

Config management (`list`, `add`, `sync`, `tools`, …) works on both `praisonai-mcp` and `praisonai mcp`.
Full capability registry requires `praisonai` co-install (`_wrapper_bridge`).

## Three MCP layers (do not conflate)

| Layer | Package | Role |
|-------|---------|------|
| Client | `praisonaiagents[mcp]` | Connect agents to external MCP servers |
| Light server | `praisonai-code` (`praisonai serve mcp`) | Basic `ToolsMCPServer` |
| Heavy host | `praisonai-mcp` (this package) | Full capability/recipe MCP server |

## Stack

```
praisonaiagents  (MCP client protocols)
   └── praisonai-mcp  (this package)
        └── praisonai  (wrapper shims: praisonai.mcp_server.*)
```

Boundary details: `src/praisonai/tests/PRAISONAI_MCP_MANIFEST.md`.
