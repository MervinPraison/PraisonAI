# PraisonAI Logging Guide

This guide explains how to enable, configure, and view logging in PraisonAI applications.

## Overview

PraisonAI provides comprehensive logging capabilities that help you debug your applications, monitor agent activities, and track system behavior. The logging system is built on Python's standard `logging` module and enhanced with Rich console formatting for better readability.

## Quick Start

To enable detailed logging, set the `LOGLEVEL` environment variable:

```bash
export LOGLEVEL=DEBUG
python your_app.py
```

## Logging Levels

PraisonAI supports all standard Python logging levels:

- **CRITICAL**: Only critical errors that may cause system failure
- **ERROR**: Error events that might still allow the application to continue
- **WARNING**: Warning messages for potentially harmful situations (default for some modules)
- **INFO**: Informational messages about general application flow (default)
- **DEBUG**: Detailed information for debugging purposes

## Configuration Methods

### 1. Environment Variable (Recommended)

Set the `LOGLEVEL` environment variable before running your application:

```bash
# Enable debug logging for all modules
export LOGLEVEL=DEBUG

# Or set it inline
LOGLEVEL=DEBUG python your_app.py
```

### 2. Programmatic Configuration

You can also configure logging programmatically in your Python code:

```python
import logging
from rich.logging import RichHandler

# Configure logging with Rich handler
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
```

### 3. Module-Specific Logging

Control logging for specific modules:

```python
import logging

# Set specific module to DEBUG while keeping others at INFO
logging.getLogger('praisonaiagents.agent').setLevel(logging.DEBUG)
logging.getLogger('praisonaiagents.task').setLevel(logging.DEBUG)
```

## What Gets Logged

### Agent Activities
- Agent initialization and configuration
- Task assignments and execution
- Tool usage and results
- Self-reflection iterations
- Delegation between agents

### Task Execution
- Task start and completion
- Context passing between tasks
- Guardrail validations and retries
- Output generation

### LLM Interactions
- Model selection and configuration
- API calls and responses
- Token usage (when available)
- Error handling and retries

### Memory Operations
- Memory storage and retrieval
- Entity recognition and updates
- Context window management

### Tool Usage
- Tool registration and discovery
- Tool execution with parameters
- Results and error handling

## Example: Viewing All Logs

Here's a complete example showing how to enable and view all logging:

```python
# test_logging.py
import os
import logging
from rich.logging import RichHandler

# Set environment variable
os.environ['LOGLEVEL'] = 'DEBUG'

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(filename)s:%(lineno)d %(levelname)s %(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)

# Your PraisonAI code
from praisonaiagents import Agent, Task, PraisonAIAgents

# Create agents
researcher = Agent(
    name="Researcher",
    role="Research Specialist",
    goal="Find information about AI logging best practices",
    backstory="You are an expert at finding and analyzing technical information"
)

writer = Agent(
    name="Writer", 
    role="Technical Writer",
    goal="Create clear documentation from research",
    backstory="You excel at explaining technical concepts clearly"
)

# Create tasks
research_task = Task(
    name="research_logging",
    description="Research best practices for logging in AI applications",
    expected_output="A list of logging best practices with explanations",
    agent=researcher
)

writing_task = Task(
    name="write_guide",
    description="Write a concise guide based on the research",
    expected_output="A well-structured guide about AI logging",
    agent=writer,
    context=[research_task]
)

# Run the agents
agents = PraisonAIAgents(
    agents=[researcher, writer],
    tasks=[research_task, writing_task],
    verbose=True
)

result = agents.start()
print(f"Final result: {result}")
```

Run with:
```bash
python test_logging.py
```

## UI-Specific Logging

### Gradio UI
```bash
export GRADIO_LOGLEVEL=DEBUG
praisonai ui --ui gradio
```

### Chainlit UI
The Chainlit-based UIs use the same `LOGLEVEL` environment variable:
```bash
export LOGLEVEL=DEBUG
praisonai ui
```

## Advanced Logging Features

### 1. Error Log Collection

PraisonAI maintains a global `error_logs` list for debugging:

```python
from praisonaiagents.main import error_logs

# After running your agents
if error_logs:
    print("Errors encountered:")
    for error in error_logs:
        print(f"- {error}")
```

### 2. Custom Log Handlers

Add custom handlers for specific logging needs:

```python
import logging

# Add file handler
file_handler = logging.FileHandler('praisonai.log')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(
    logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
)

logger = logging.getLogger('praisonaiagents')
logger.addHandler(file_handler)
```

### 3. Suppressing Third-Party Logs

PraisonAI automatically suppresses noisy third-party library logs. To re-enable them:

```python
import logging

# Re-enable specific library logs
logging.getLogger('litellm').setLevel(logging.INFO)
logging.getLogger('chromadb').setLevel(logging.INFO)
```

## Troubleshooting

### Not Seeing Expected Logs?

1. **Check the log level**: Ensure `LOGLEVEL` is set correctly
   ```bash
   echo $LOGLEVEL  # Should show DEBUG, INFO, etc.
   ```

2. **Verify module names**: Use the correct module path
   ```python
   # Correct
   logging.getLogger('praisonaiagents.agent').setLevel(logging.DEBUG)
   
   # Incorrect
   logging.getLogger('agent').setLevel(logging.DEBUG)
   ```

3. **Check for log suppression**: Some modules may have logging disabled
   ```python
   # Check if handlers are present
   logger = logging.getLogger('praisonaiagents')
   print(f"Handlers: {logger.handlers}")
   print(f"Level: {logger.level}")
   ```

### Too Many Logs?

Increase the log level or disable specific modules:

```python
# Reduce overall logging
os.environ['LOGLEVEL'] = 'WARNING'

# Or disable specific modules
logging.getLogger('praisonaiagents.telemetry').setLevel(logging.WARNING)
logging.getLogger('praisonaiagents.memory').setLevel(logging.WARNING)
```

## Best Practices

1. **Development**: Use `DEBUG` level to see all activities
2. **Testing**: Use `INFO` level for general flow tracking
3. **Production**: Use `WARNING` or `ERROR` to reduce noise
4. **Debugging Issues**: Temporarily enable `DEBUG` for specific modules
5. **Log Files**: Consider writing logs to files for production environments

## Environment Variables Summary

| Variable | Description | Default | Options |
|----------|-------------|---------|---------|
| `LOGLEVEL` | Main logging level | INFO | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `GRADIO_LOGLEVEL` | Gradio UI logging | INFO | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `PRAISONAI_TELEMETRY_DISABLED` | Disable telemetry | false | true, false |
| `LITELLM_TELEMETRY` | LiteLLM telemetry | false | true, false |

## Related Documentation

- [PraisonAI Agents Documentation](https://docs.praison.ai)
- [Python Logging Documentation](https://docs.python.org/3/library/logging.html)
- [Rich Logging Documentation](https://rich.readthedocs.io/en/latest/logging.html)