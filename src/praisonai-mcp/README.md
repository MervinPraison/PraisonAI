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

## Connect your editor or agent

One command puts PraisonAI in Cursor, VS Code, Claude Code, Claude Desktop,
Codex, Gemini CLI, Windsurf, Zed, Kiro, Antigravity, Cline, Continue,
OpenCode, Goose, LM Studio or Copilot CLI:

```bash
praisonai connect                     # installed / connected / last active, per client
praisonai connect cursor              # writes ~/.cursor/mcp.json (diff + backup), then "N tools ready"
praisonai connect --all               # every installed client
praisonai connect codex --agents agents.yaml --tools 'ask_*'   # scope: only your agents
praisonai connect cursor --print      # one-click deep link, command and JSON; writes nothing
praisonai connect --remove            # undo everywhere
```

- Writes are idempotent, keep a `.praisonai.bak` copy, and touch only the
  `praisonai` entry (TOML comments and other servers stay).
- Secrets are never written: set keys are referenced in each client's own
  syntax (`${env:OPENAI_API_KEY}`, `${OPENAI_API_KEY}`, Codex `env_vars`).
- After writing, a real MCP `initialize` + `tools/list` runs against the
  exact command that was configured.
- The server records which client connected (`clientInfo`) and when, in
  `connections.json` under the PraisonAI MCP folder; `praisonai connect`
  shows it as "last active". Nothing leaves the machine.
- `--tools` and `--agents` are server arguments (`serve --tools/--agents`),
  so the scope holds in every client, one-click links included.
- `praisonai_mcp.connect.export_catalog(spec)` returns the same catalog as
  JSON; PraisonAIUI's Connect page renders it.

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
