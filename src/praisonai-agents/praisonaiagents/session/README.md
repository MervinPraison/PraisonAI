# Session Persistence for PraisonAI Agents

This module provides automatic session persistence with zero configuration.

## Quick Start

```python
from praisonaiagents import Agent

# With session persistence (auto-enabled)
agent = Agent(
    name="Assistant",
    session_id="my-session-123"
)
agent.start("Hello, my name is Alice")

# Later, in a new process - history is restored automatically
agent = Agent(
    name="Assistant", 
    session_id="my-session-123"
)
agent.start("What is my name?")  # Agent remembers: "Alice"
```

## How It Works

When you provide a `session_id` to an Agent:

1. **Automatic Persistence**: Conversation history is automatically saved to disk
2. **Automatic Restoration**: When a new Agent is created with the same `session_id`, history is restored
3. **Zero Configuration**: No database setup required - uses JSON files by default

### Default Storage Location

Sessions are stored in: `~/.praison/sessions/{session_id}.json`

### Session File Format

```json
{
  "session_id": "my-session-123",
  "messages": [
    {"role": "user", "content": "Hello", "timestamp": 1704153600.0},
    {"role": "assistant", "content": "Hi there!", "timestamp": 1704153601.5}
  ],
  "created_at": "2026-01-02T04:00:00+00:00",
  "updated_at": "2026-01-02T04:01:00+00:00",
  "agent_name": "Assistant"
}
```

## Behavior Matrix

| Scenario | Behavior |
|----------|----------|
| `session_id` provided, no DB | JSON persistence (auto) |
| `session_id` provided, with DB | DB adapter used |
| No `session_id`, same Agent instance | In-memory only |
| No `session_id`, new Agent instance | No history |

## Advanced Usage

### Direct Session Store Access

```python
from praisonaiagents.session import get_default_session_store

store = get_default_session_store()

# Add messages
store.add_user_message("session-123", "Hello")
store.add_assistant_message("session-123", "Hi there!")

# Get history
history = store.get_chat_history("session-123")
# [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi there!"}]

# List all sessions
sessions = store.list_sessions()

# Delete a session
store.delete_session("session-123")
```

### Custom Session Directory

```python
from praisonaiagents.session import DefaultSessionStore

store = DefaultSessionStore(
    session_dir="/custom/path/sessions",
    max_messages=200,  # Default: 100
    lock_timeout=10.0,  # Default: 5.0 seconds
)
```

### Using with DB Adapter

When a DB adapter is provided, it takes precedence over JSON persistence:

```python
from praisonaiagents import Agent
from praisonai.db import PostgresAdapter

agent = Agent(
    name="Assistant",
    session_id="my-session",
    db=PostgresAdapter(connection_string="...")
)
```

## Multi-Process Safety

The session store uses file locking to ensure safe concurrent access:

- **Unix**: Uses `fcntl.flock()` for file locking
- **Windows**: Uses `msvcrt.locking()` for file locking
- **Atomic Writes**: Uses temp file + rename to prevent corruption

Multiple processes can safely read/write to the same session.

## Context Caching

For cost optimization, use `prompt_caching=True` with Anthropic models:

```python
agent = Agent(
    name="Assistant",
    session_id="my-session",
    prompt_caching=True,  # Enables Anthropic prompt caching
)
```

This caches the system prompt, reducing token costs for repeated conversations.

## API Reference

### DefaultSessionStore

```python
class DefaultSessionStore:
    def __init__(
        self,
        session_dir: Optional[str] = None,  # Default: ~/.praison/sessions/
        max_messages: int = 100,
        lock_timeout: float = 5.0,
    ): ...
    
    def add_message(self, session_id: str, role: str, content: str) -> bool: ...
    def add_user_message(self, session_id: str, content: str) -> bool: ...
    def add_assistant_message(self, session_id: str, content: str) -> bool: ...
    def get_chat_history(self, session_id: str, max_messages: int = None) -> List[Dict]: ...
    def get_session(self, session_id: str) -> SessionData: ...
    def clear_session(self, session_id: str) -> bool: ...
    def delete_session(self, session_id: str) -> bool: ...
    def list_sessions(self, limit: int = 50) -> List[Dict]: ...
    def session_exists(self, session_id: str) -> bool: ...
```

### SessionData

```python
@dataclass
class SessionData:
    session_id: str
    messages: List[SessionMessage]
    created_at: str
    updated_at: str
    agent_name: Optional[str]
    user_id: Optional[str]
    metadata: Dict[str, Any]
    
    def get_chat_history(self, max_messages: int = None) -> List[Dict[str, str]]: ...
```

### SessionMessage

```python
@dataclass
class SessionMessage:
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: float
    metadata: Dict[str, Any]
```
