# Remote Agent Connectivity

This directory contains examples demonstrating PraisonAI's remote agent connectivity feature, which allows you to connect to agents running on different servers, similar to Google ADK's agent connectivity pattern.

## Overview

The remote agent connectivity feature enables:
- **Direct agent-to-agent connectivity** across networks
- **Session-based communication** with remote agents  
- **Google ADK-like API patterns** for familiar usage
- **Automatic connection management** and error handling

## Quick Start

### 1. Start a Remote Agent Server

```bash
# Start a simple remote agent server
python remote_agent_server.py

# Or start multiple agents on one server
python remote_agent_server.py --multiple
```

### 2. Connect from Client

```python
from praisonaiagents import Session

# Connect to remote agent (similar to Google ADK)
session = Session(agent_url="192.168.1.10:8000/agent")

# Send messages to the remote agent
response = session.chat("Hello from the client!")
print(response)

# Alternative method (Google ADK pattern)  
response = session.send_message("What can you help me with?")
print(response)
```

## Examples

- **`remote_agent_server.py`** - Set up agents as remote servers
- **`remote_agent_example.py`** - Connect to and communicate with remote agents

## API Comparison

### Google ADK Pattern
```python
from adk.agent import Agent
from adk.session import Session

session = Session(agent_url="192.168.1.10:8000")
response = session.send_message("Hello!")
```

### PraisonAI Pattern  
```python
from praisonaiagents import Session

session = Session(agent_url="192.168.1.10:8000/agent")
response = session.chat("Hello!")
# OR
response = session.send_message("Hello!")  # Google ADK compatibility
```

## Key Features

### ✅ **Seamless Connectivity**
- Automatic protocol detection (http/https)
- Connection testing and validation
- Configurable timeouts

### ✅ **Error Handling**
- Clear error messages for connection issues
- Graceful handling of network problems
- Appropriate fallbacks for unavailable services

### ✅ **Backward Compatibility**
- Existing local agent functionality unchanged
- Session API works for both local and remote scenarios
- No breaking changes to current code

### ✅ **Flexible Configuration**
- Support for IP:port format (`192.168.1.10:8000`)
- Full URL format (`http://server.com:8000/agent`)
- Customizable endpoints and paths

## Usage Patterns

### Single Remote Agent
```python
# Connect to a specific remote agent
session = Session(agent_url="192.168.1.10:8000/agent")
response = session.chat("Hello from remote client!")
```

### Multiple Remote Agents
```python
# Connect to different specialized agents
research_session = Session(agent_url="192.168.1.10:8000/research")
coding_session = Session(agent_url="192.168.1.10:8000/coding")

research_response = research_session.chat("Find info about AI trends")
coding_response = coding_session.chat("Help me debug this Python code")
```

### Error Handling
```python
try:
    session = Session(agent_url="192.168.1.10:8000/agent")
    response = session.chat("Test message")
    print(f"Response: {response}")
except ConnectionError as e:
    print(f"Failed to connect: {e}")
```

## Network Configuration

### Server Setup
```python
# Create and launch agent server
agent = Agent(name="RemoteAgent", role="Assistant")
agent.launch(path="/agent", port=8000, host="0.0.0.0")
```

### Client Connection
```python
# Connect from any network location
session = Session(agent_url="<server-ip>:8000/agent")
```

## Limitations for Remote Sessions

When using remote agent sessions, certain local operations are not available:
- **Memory operations** (`session.memory.*`)
- **Knowledge operations** (`session.knowledge.*`) 
- **Local agent creation** (`session.Agent(...)`)
- **State management** (`session.save_state/restore_state`)

This design keeps remote and local operations clearly separated.

## Testing

Run the examples to test the functionality:

```bash
# Terminal 1: Start server
python remote_agent_server.py

# Terminal 2: Test client (update IP as needed)
python remote_agent_example.py
```

## Integration with Existing Code

The remote connectivity feature integrates seamlessly with existing PraisonAI code:

```python
# Existing local code works unchanged
local_session = Session(session_id="local_chat")
local_agent = local_session.Agent(name="LocalAgent", role="Assistant")

# New remote connectivity
remote_session = Session(agent_url="remote-server:8000/agent")
remote_response = remote_session.chat("Hello from remote!")
```

This provides a smooth migration path for applications that need to scale across multiple servers.