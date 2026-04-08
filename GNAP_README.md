# GNAP (Git-Native Agent Persistence) Plugin

GNAP provides git-native task persistence for PraisonAI multi-agent workflows, enabling distributed coordination and crash recovery without requiring external services like Redis or Celery.

## Features

- 🔄 **Durable task persistence** using git commits and `.gnap` folders
- 🌐 **Distributed coordination** via shared git repositories  
- 📈 **Complete audit trail** through git history
- 🚀 **Zero-server architecture** - no Redis, Celery, or external services
- 🔧 **StorageBackendProtocol compliance** for seamless PraisonAI integration
- 🧵 **Thread-safe operations** with atomic file writes
- 🌿 **Branch-based workflow isolation** for multi-agent coordination

## Installation

```bash
pip install praisonai-tools[gnap]
```

## Quick Start

### As a Storage Backend

```python
from praisonai_tools.plugins.gnap import GNAPStorageBackend

# Initialize with git repository
backend = GNAPStorageBackend(repo_path="./my_project")

# Save task state (auto-commits to git)
backend.save("task_123", {
    "status": "completed",
    "agent": "researcher", 
    "results": ["finding1", "finding2"]
})

# Load task state (survives crashes)
task = backend.load("task_123")
print(f"Status: {task['status']}")

# List all tasks
tasks = backend.list_keys()
```

### As Agent Tools

```python
from praisonaiagents import Agent
from praisonai_tools.plugins.gnap import (
    gnap_save_state, gnap_load_state, gnap_list_tasks, gnap_get_status
)

# Create agent with GNAP tools
agent = Agent(
    name="persistent_agent",
    instructions="You manage tasks using GNAP for persistence.",
    tools=[gnap_save_state, gnap_load_state, gnap_list_tasks, gnap_get_status]
)

# Agent can now save/load state across crashes
response = agent.start("Save my research progress on AI trends")
```

## Configuration

Set these environment variables to configure GNAP:

```bash
# Git repository path (default: current directory)
export GNAP_REPO_PATH="./my_project"

# Auto-commit on saves (default: true)  
export GNAP_AUTO_COMMIT="true"

# Agent identifier for multi-agent coordination
export GNAP_AGENT_ID="researcher_bot"
```

## Storage Structure

GNAP creates this structure in your git repository:

```
.gnap/
├── config.json              # GNAP configuration
└── tasks/
    ├── task_001.json         # Task state files
    ├── research_123.json
    └── analysis_456.json
```

Each task file contains:

```json
{
  "_gnap": {
    "task_id": "research_123",
    "timestamp": "2026-04-08T06:00:00Z",
    "branch": "main", 
    "agent_id": "researcher_bot"
  },
  "status": "completed",
  "results": ["finding1", "finding2"],
  "custom_field": "custom_value"
}
```

## Multi-Agent Workflows

### Branch Isolation

Each workflow can run on its own git branch:

```python
from praisonai_tools.plugins.gnap import gnap_create_workflow_branch, gnap_merge_workflow

# Agent 1: Create isolated workflow
branch = gnap_create_workflow_branch("data_analysis_pipeline") 
# All GNAP operations now happen on this branch

# ... workflow execution ...

# Agent 2: Merge completed workflow back to main
gnap_merge_workflow("gnap-workflow-data_analysis_pipeline")
```

### Agent Coordination

Multiple agents can work on the same repository:

```python
# Agent 1: Researcher
os.environ["GNAP_AGENT_ID"] = "researcher"
gnap_save_state("market_research", {"status": "completed", "findings": [...]})

# Agent 2: Writer  
os.environ["GNAP_AGENT_ID"] = "writer"
research_data = gnap_load_state("market_research")
gnap_save_state("blog_post", {"status": "in_progress", "source": research_data})

# Agent 3: Monitor
status = gnap_get_status()
print(f"Total tasks: {status['total_tasks']}")
print(f"By agent: {status['by_agent']}")
```

## Crash Recovery

Tasks survive process crashes since they're stored in git:

```python
# Before crash
gnap_save_state("long_running_task", {"status": "in_progress", "step": 5})

# After crash/restart  
task = gnap_load_state("long_running_task") 
if task and task["status"] == "in_progress":
    print(f"Resuming from step {task['step']}")
    # Continue where we left off
```

## Integration with PraisonAI Storage

Use GNAP as a storage backend anywhere in PraisonAI:

```python
# Via storage backend factory
from praisonaiagents.storage.backends import get_backend

backend = get_backend("gnap", repo_path="./project")
backend.save("session_123", {"messages": [...], "context": {...}})
```

## Tool Functions Reference

### `gnap_save_state(task_id: str, state: Dict) -> str`
Save task state with git persistence.

### `gnap_load_state(task_id: str) -> Dict`  
Load task state from storage.

### `gnap_list_tasks(prefix: str = "", status_filter: str = "") -> List[Dict]`
List tasks with optional filtering.

### `gnap_get_status() -> Dict`
Get comprehensive status summary.

### `gnap_commit(message: str) -> str`
Manually commit current state.

### `gnap_get_history(task_id: str) -> List[Dict]`
Get git commit history for a task.

### `gnap_create_workflow_branch(workflow_id: str) -> str`
Create isolated branch for workflow.

### `gnap_merge_workflow(workflow_branch: str) -> str`
Merge completed workflow to main.

## Advanced Usage

### Custom Git Operations

```python
from praisonai_tools.plugins.gnap import GNAPStorageBackend

backend = GNAPStorageBackend(repo_path="./project")

# Get task history
history = backend.get_task_history("important_task")
for commit in history:
    print(f"{commit['timestamp']}: {commit['message']}")

# Create workflow branch
branch = backend.create_workflow_branch("feature_development")
print(f"Working on branch: {branch}")

# Get comprehensive status
status = backend.get_status_summary()
print(f"Tasks by status: {status['by_status']}")
print(f"Recent activity: {status['recent_activity'][:3]}")
```

### Thread Safety

GNAP is thread-safe for concurrent agent operations:

```python
import threading
from praisonai_tools.plugins.gnap import gnap_save_state

def agent_worker(agent_id, task_count):
    for i in range(task_count):
        gnap_save_state(f"{agent_id}_task_{i}", {
            "status": "completed",
            "agent": agent_id,
            "data": f"result_{i}"
        })

# Multiple agents working concurrently
threads = []
for agent_id in ["agent1", "agent2", "agent3"]:
    t = threading.Thread(target=agent_worker, args=(agent_id, 10))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

# All tasks safely persisted
all_tasks = gnap_list_tasks()
print(f"Total tasks: {len(all_tasks)}")
```

## Troubleshooting

### GitPython Not Found
```bash
pip install praisonai-tools[gnap]  # Installs GitPython
```

### Git Repository Issues
```python
# GNAP auto-initializes git repos, but you can do it manually:
import git
repo = git.Repo.init("./my_project")
```

### Performance with Large Repositories
```python
# Use branch isolation for large workflows
gnap_create_workflow_branch("large_workflow")
# Work on isolated branch, merge when complete
gnap_merge_workflow("gnap-workflow-large_workflow")
```

## Architecture

GNAP follows PraisonAI's protocol-driven architecture:

- **Plugin Protocol**: Implements `PluginProtocol` for lifecycle management
- **Storage Protocol**: Implements `StorageBackendProtocol` for seamless integration  
- **Tool Functions**: Provides `@tool` decorated functions for agent use
- **Entry Points**: Registered via `praisonai-tools[gnap]` for discovery
- **Lazy Loading**: GitPython imported only when needed

## Contributing

GNAP is part of [PraisonAI-Tools](https://github.com/MervinPraison/PraisonAI-Tools). See the repository for contribution guidelines.