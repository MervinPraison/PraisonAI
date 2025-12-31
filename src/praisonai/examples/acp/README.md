# ACP (Agent Client Protocol) Examples

This directory contains examples for using PraisonAI with the Agent Client Protocol (ACP).

## What is ACP?

The Agent Client Protocol (ACP) is a standardized JSON-RPC 2.0 protocol that allows code editors and IDEs to communicate with AI coding agents. It enables seamless integration between PraisonAI and editors like:

- **Zed**
- **JetBrains IDEs** (IntelliJ, PyCharm, WebStorm, etc.)
- **VSCode** (via extensions)
- **Toad**

## Quick Start

### CLI Usage

```bash
# Start ACP server with defaults
praisonai acp

# Enable debug logging
praisonai acp --debug

# Allow file writes
praisonai acp --allow-write

# Use a specific model
praisonai acp -m gpt-4o

# Resume last session
praisonai acp --resume --last
```

### Python API

```python
from praisonai.acp import serve

serve(
    workspace=".",
    debug=True,
    allow_write=True,
)
```

## Editor Configuration

### Zed

Add to `~/.config/zed/settings.json`:

```json
{
  "agent_servers": {
    "PraisonAI": {
      "command": "praisonai",
      "args": ["acp"],
      "env": {}
    }
  }
}
```

### JetBrains

Add to `~/.jetbrains/acp.json`:

```json
{
  "agent_servers": {
    "PraisonAI": {
      "command": "praisonai",
      "args": ["acp"],
      "env": {}
    }
  }
}
```

### Toad

```bash
toad acp "praisonai acp"
```

## Examples

- `basic_acp_server.py` - Simple ACP server with default settings
- `custom_agent_acp.py` - ACP server with a custom agent

## CLI Options

| Option | Description |
|--------|-------------|
| `-w, --workspace` | Workspace root directory |
| `-a, --agent` | Agent name or config file |
| `-m, --model` | LLM model to use |
| `-r, --resume` | Resume session by ID |
| `--last` | Resume the last session |
| `--approve` | Approval mode: manual, auto, scoped |
| `--read-only` | Read-only mode (default) |
| `--allow-write` | Allow file writes |
| `--allow-shell` | Allow shell commands |
| `--debug` | Enable debug logging |

## Installation

```bash
pip install praisonai[acp]
```

## Protocol Details

ACP uses JSON-RPC 2.0 over stdio:
- **stdin**: Receives JSON-RPC requests from the client
- **stdout**: Sends JSON-RPC responses to the client
- **stderr**: Debug/log output (never pollutes stdout)

### Supported Methods

**Agent Methods (client → agent):**
- `initialize` - Negotiate protocol version and capabilities
- `authenticate` - Optional authentication
- `session/new` - Create a new session
- `session/load` - Load an existing session
- `session/prompt` - Send user message
- `session/cancel` - Cancel ongoing operations
- `session/set_mode` - Change operating mode

**Client Methods (agent → client):**
- `session/update` - Send progress updates
- `session/request_permission` - Request user approval
- `fs/read_text_file` - Read file contents
- `fs/write_text_file` - Write file contents
- `terminal/create` - Create terminal
- `terminal/output` - Get terminal output
