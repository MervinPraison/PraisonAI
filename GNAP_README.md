# GNAP Storage Backend for PraisonAI Tools

GNAP (Git-Native Agent Protocol) is a zero-server durable task queuing storage backend that extends PraisonAI's storage capabilities with git-based persistence.

## Features

- **🔄 Durable Task Persistence**: Tasks survive crashes and restarts via git commits
- **🌐 Distributed Coordination**: Multiple agents can coordinate via shared git repositories
- **📈 Complete Audit Trail**: Every task change is tracked through git history
- **🚀 Zero Infrastructure**: No Redis, Celery, or external services required
- **🔧 Compatible**: Implements StorageBackendProtocol for seamless integration
- **🧪 Git-Native**: Uses standard git operations for coordination

## Installation

Install PraisonAI-Tools with GNAP support:

```bash
# Basic installation
pip install praisonai-tools

# With optional git dependencies
pip install "praisonai-tools[gnap]"
```

## Quick Start

### Basic Usage

```python
from praisonai_tools.gnap import GNAPStorageBackend

# Initialize GNAP backend
backend = GNAPStorageBackend(repo_path="./my_project")

# Save a task
task = {
    "id": "task_123",
    "status": "pending", 
    "agent": "researcher",
    "description": "Research AI trends",
    "payload": {"query": "latest AI developments"}
}
backend.save("task_123", task)

# Load the task
loaded_task = backend.load("task_123")
print(f"Task status: {loaded_task['status']}")

# List all tasks
all_tasks = backend.list_keys()
print(f"Total tasks: {len(all_tasks)}")
```

### Integration with PraisonAI Storage System

```python
from praisonaiagents.storage.backends import get_backend

# Use GNAP via storage backend factory (once registered)
backend = get_backend("gnap", repo_path="./my_project")

# Now use like any other storage backend
backend.save("session_001", {"messages": [], "status": "active"})
data = backend.load("session_001")
```

### Multi-Agent Coordination

```python
# Agent A saves tasks
backend_a = GNAPStorageBackend(repo_path="./shared_project")
backend_a.save("analysis_task", {
    "id": "analysis_task",
    "status": "pending",
    "assigned_to": "data_analyst",
    "depends_on": []
})

# Agent B reads and updates tasks (same repository)
backend_b = GNAPStorageBackend(repo_path="./shared_project")  
task = backend_b.load("analysis_task")
task["status"] = "in_progress"
task["started_at"] = "2026-04-08T06:00:00Z"
backend_b.save("analysis_task", task)

# Both agents see the update through git history
history = backend_a.get_git_history("analysis_task")
print(f"Task has {len(history)} commits")
```

### Remote Synchronization

```python
backend = GNAPStorageBackend(
    repo_path="./distributed_project",
    auto_commit=True
)

# Sync with remote for distributed coordination
success = backend.sync_with_remote("origin")
if success:
    print("Successfully synced with remote")
else:
    print("Sync failed - check for conflicts")
```

## Configuration Options

```python
backend = GNAPStorageBackend(
    repo_path=".",                    # Git repository path
    gnap_folder=".gnap",             # Folder name for GNAP storage
    auto_commit=True,                # Auto-commit changes to git
    commit_author="Agent Name",      # Git commit author
    commit_email="agent@ai.com",     # Git commit email
    branch="main"                    # Git branch to use
)
```

## GNAP Folder Structure

GNAP creates a structured folder layout in your repository:

```
.gnap/
├── config.json          # GNAP configuration metadata
├── tasks/               # Task storage (JSON files)
│   ├── task_001.json
│   ├── task_002.json
│   └── ...
├── agents/              # Agent coordination (future use)
└── status/              # Status tracking (future use)
```

## Advanced Features

### Git History Analysis

```python
# Get complete history
history = backend.get_git_history()
for commit in history:
    print(f"{commit['date']}: {commit['message']}")

# Get history for specific task
task_history = backend.get_git_history("task_123")
print(f"Task has {len(task_history)} changes")
```

### Status Summary

```python
summary = backend.get_status_summary()
print(f"Total tasks: {summary['total_tasks']}")
print(f"By status: {summary['status_breakdown']}")
print(f"Git initialized: {summary['git_initialized']}")
```

### Custom Git Configuration

```python
import os

# Configure via environment variables
os.environ["GIT_AUTHOR_NAME"] = "AI Research Agent"
os.environ["GIT_AUTHOR_EMAIL"] = "research@ai-lab.com"

backend = GNAPStorageBackend(repo_path="./research_project")
```

## Integration Patterns

### With PraisonAI Agents

```python
from praisonaiagents import Agent
from praisonai_tools.gnap import GNAPStorageBackend

# Create custom storage backend
storage = GNAPStorageBackend(repo_path="./agent_workspace")

# Use with agent's memory/session system
agent = Agent(
    name="persistent_agent",
    instructions="You are a research agent with durable task storage"
    # Note: Direct storage integration depends on PraisonAI version
)

# Save agent tasks manually
agent_task = {
    "agent_name": agent.name,
    "task_type": "research",
    "query": "AI safety practices",
    "status": "pending"
}
storage.save(f"agent_task_{int(time.time())}", agent_task)
```

### Distributed Task Queue

```python
import time
from datetime import datetime, timezone

def create_task_queue(repo_path):
    backend = GNAPStorageBackend(repo_path=repo_path)
    
    def enqueue_task(task_id, task_data):
        task_data.update({
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "status": "queued"
        })
        backend.save(task_id, task_data)
    
    def dequeue_task(prefix=""):
        tasks = backend.list_keys(prefix=prefix)
        for task_id in tasks:
            task = backend.load(task_id)
            if task and task.get("status") == "queued":
                task["status"] = "processing"
                task["started_at"] = datetime.now(timezone.utc).isoformat()
                backend.save(task_id, task)
                return task_id, task
        return None, None
    
    return enqueue_task, dequeue_task

# Usage
enqueue, dequeue = create_task_queue("./task_queue")

# Add tasks
enqueue("research_001", {
    "type": "research", 
    "query": "quantum computing trends"
})

# Process tasks
task_id, task = dequeue("research_")
if task:
    print(f"Processing {task_id}: {task['query']}")
```

## Best Practices

1. **Repository Setup**: Initialize git repository before using GNAP
2. **Commit Messages**: GNAP adds descriptive commit messages automatically
3. **Distributed Coordination**: Use `sync_with_remote()` for multi-machine setups
4. **Task Keys**: Use descriptive, hierarchical keys like `agent_name/task_type/task_id`
5. **Status Management**: Include `status` field in tasks for queue management
6. **Error Handling**: GNAP gracefully handles git errors and continues operation

## Troubleshooting

### Git Not Found
```bash
# Install git if missing
sudo apt-get install git  # Ubuntu/Debian
brew install git          # macOS
```

### Permission Issues
```bash
# Ensure git repository is writable
chmod -R u+w ./your_project/.git
```

### Sync Conflicts
```python
# Handle merge conflicts manually
success = backend.sync_with_remote("origin")
if not success:
    print("Manual merge required - check git status")
```

## Contributing

GNAP is part of PraisonAI-Tools. Contributions welcome:

1. Fork the [PraisonAI-Tools repository](https://github.com/MervinPraison/PraisonAI-Tools)
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

## License

MIT License - see PraisonAI-Tools repository for details.

## Related

- [PraisonAI Core](https://github.com/MervinPraison/PraisonAI) - Main framework
- [GNAP Specification](https://github.com/farol-team/gnap) - Original protocol
- [PraisonAI Documentation](https://docs.praison.ai) - Full documentation