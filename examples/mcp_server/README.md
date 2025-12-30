# PraisonAI MCP Server Examples

This directory contains examples for running PraisonAI as an MCP (Model Context Protocol) server.

## Overview

PraisonAI can expose its capabilities via MCP protocol, allowing integration with:
- Claude Desktop
- Cursor
- Windsurf
- VSCode MCP clients
- Any MCP-compatible client

## Protocol Version

These examples use MCP Protocol Version **2025-11-25**.

## Examples

### 1. STDIO Server (stdio_server.py)

Run PraisonAI as an MCP server using STDIO transport (for Claude Desktop integration).

```bash
# Run directly
python stdio_server.py

# Or via CLI
praisonai mcp serve --transport stdio
```

### 2. HTTP Stream Server (http_stream_server.py)

Run PraisonAI as an MCP server using HTTP Stream transport.

```bash
# Run directly
python http_stream_server.py

# Or via CLI
praisonai mcp serve --transport http-stream --port 8080
```

### 3. Custom Tools Server (custom_tools_server.py)

Register custom tools and expose them via MCP.

```bash
python custom_tools_server.py
```

### 4. Client Example (mcp_client_example.py)

Example of connecting to a PraisonAI MCP server as a client.

```bash
python mcp_client_example.py
```

## CLI Commands

```bash
# Start STDIO server
praisonai mcp serve --transport stdio

# Start HTTP Stream server
praisonai mcp serve --transport http-stream --port 8080

# Start with authentication
praisonai mcp serve --transport http-stream --api-key YOUR_KEY

# List available tools
praisonai mcp list-tools

# List available resources
praisonai mcp list-resources

# List available prompts
praisonai mcp list-prompts

# Generate client configuration
praisonai mcp config-generate --client claude-desktop

# Check server health
praisonai mcp doctor
```

## Client Configuration

### Claude Desktop

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "praisonai": {
      "command": "praisonai",
      "args": ["mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

### Cursor

Add to Cursor settings:

```json
{
  "mcpServers": {
    "praisonai": {
      "command": "praisonai",
      "args": ["mcp", "serve", "--transport", "stdio"]
    }
  }
}
```

## Environment Variables

Set the following environment variables for full functionality:

```bash
export OPENAI_API_KEY=your_key
export ANTHROPIC_API_KEY=your_key  # Optional
export GOOGLE_API_KEY=your_key     # Optional
```

## Available Tools

Run `praisonai mcp list-tools` to see all available tools, including:

- `praisonai.chat.completion` - Chat with LLM
- `praisonai.agent.chat` - Chat with an agent
- `praisonai.agent.run` - Run a task with an agent
- `praisonai.workflow.run` - Run a workflow
- `praisonai.images.generate` - Generate images
- `praisonai.audio.transcribe` - Transcribe audio
- `praisonai.embed.create` - Create embeddings
- `praisonai.memory.*` - Memory operations
- `praisonai.knowledge.*` - Knowledge base operations
- And many more...

## Available Resources

- `praisonai://memory/sessions` - List memory sessions
- `praisonai://workflows` - List available workflows
- `praisonai://tools` - List available tools
- `praisonai://agents` - List agent configurations
- `praisonai://knowledge/sources` - List knowledge sources
- `praisonai://config` - Get current configuration
- `praisonai://mcp/status` - Get MCP server status

## Available Prompts

- `deep-research` - Generate deep research prompts
- `code-review` - Generate code review prompts
- `workflow-auto` - Generate workflow auto-generation prompts
- `guardrail-check` - Generate guardrail check prompts
- `context-engineering` - Generate context engineering prompts
- `eval-criteria` - Generate evaluation criteria prompts
- `agent-instructions` - Generate agent instructions prompts
