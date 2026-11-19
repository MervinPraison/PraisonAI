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

## Sign-in over HTTP (OAuth 2.1)

Locally nothing changes: stdio and `--host 127.0.0.1` need no sign-in. Bind
to a network address without `--api-key` and the server signs clients in
itself, following the MCP authorization spec:

```bash
PRAISONAI_MCP_OWNER_KEY=… praisonai mcp serve --transport http-stream \
  --host 0.0.0.0 --issuer https://agents.example.com     # --oauth also turns it on for localhost
```

- Editors find the sign-in on their own: `401` + `WWW-Authenticate:
  Bearer resource_metadata=…`, Protected Resource Metadata (RFC 9728) and
  Authorization Server Metadata (RFC 8414).
- Authorization code with PKCE S256 only; public clients; the token audience
  is the requested `resource` (RFC 8707).
- Dynamic Client Registration and Client ID Metadata Documents. VS Code, Zed,
  Kiro, Antigravity, Claude Code, ChatGPT/Codex, Goose and OpenCode prove
  who they are by their domain, and Cursor, VS Code, Claude and ChatGPT
  callbacks are recognised, so they show as **Verified**. Loopback redirects
  show as **On this device** and may use any port (RFC 8252). Any other app
  gets a warning that names where you will be sent.
- The consent page asks once for the owner key (`PRAISONAI_MCP_OWNER_KEY`,
  or one printed at start). It lists the scopes in plain words, each with a
  checkbox, offers **Allow read-only**, and lets you choose how long access
  lasts. **Deny** returns `error=access_denied` to the app at once.
- Refresh tokens rotate and work once. Replaying an old one disconnects the
  app.
- Headless: the device flow (`POST /oauth/device`, then open
  `/oauth/device/verify` and enter `ABCD-EFGH`).
- Connected apps: `GET /oauth/apps` and `POST /oauth/apps/<id>/revoke`
  (owner key as Bearer). Apps can also revoke a token themselves (RFC 7009).
- Only SHA-256 hashes of tokens are stored, in `oauth.json` (mode 0600) in
  the PraisonAI MCP folder.

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
