# Recipe Background Tasks Example

This example demonstrates how to run recipes and agents as background tasks.

## Prerequisites

```bash
pip install praisonai praisonaiagents
export OPENAI_API_KEY="your-api-key"
```

## Python Example

```bash
python example_background.py
```

## CLI Examples

### Submit a recipe as background task

```bash
# Submit recipe to background
praisonai background submit --recipe my-recipe --input '{"query": "test"}'

# Check status
praisonai background status <task_id>

# List all tasks
praisonai background list

# Cancel a task
praisonai background cancel <task_id>

# Clear completed tasks
praisonai background clear
```

### Run recipe with --background flag

```bash
# Run recipe in background
praisonai recipe run my-recipe --background

# With input
praisonai recipe run my-recipe --background --input '{"topic": "AI"}'

# With session ID
praisonai recipe run my-recipe --background --session-id session_123
```

## Key Features

- **Async Execution**: Tasks run in the background without blocking
- **Progress Tracking**: Monitor task progress and status
- **Cancellation**: Cancel running tasks when needed
- **Result Retrieval**: Get results when tasks complete
- **Concurrency Control**: Limit concurrent tasks

## Safe Defaults

| Setting | Default | Description |
|---------|---------|-------------|
| `timeout_sec` | 300 | Maximum execution time |
| `max_concurrent` | 5 | Maximum concurrent tasks |
| `cleanup_delay_sec` | 3600 | Auto-cleanup delay |
