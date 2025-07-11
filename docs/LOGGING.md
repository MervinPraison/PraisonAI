# PraisonAI Logging Guide

This guide explains how to enable and use logging in PraisonAI to debug your applications.

## Quick Start

To enable debug logging, set the `LOGLEVEL` environment variable before running your script:

```bash
export LOGLEVEL=DEBUG
python your_script.py
```

Or set it inline:
```bash
LOGLEVEL=DEBUG python your_script.py
```

## Logging Levels

PraisonAI supports standard Python logging levels:
- `DEBUG` - Detailed information for debugging
- `INFO` - General informational messages (default)
- `WARNING` - Warning messages
- `ERROR` - Error messages
- `CRITICAL` - Critical error messages

## Programmatic Configuration

You can also set the log level programmatically:

```python
import os
# Set before importing PraisonAI
os.environ['LOGLEVEL'] = 'DEBUG'

from praisonai import PraisonAI
```

## Example: Debug Logging

```python
#!/usr/bin/env python3
import os
import logging

# Enable debug logging
os.environ['LOGLEVEL'] = 'DEBUG'

# Configure logging format (optional)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from praisonai import PraisonAI

# Your PraisonAI code here
praison = PraisonAI(agent_file='agents.yaml')
result = praison.run()
```

## What Debug Logging Shows

When debug logging is enabled, you'll see:
- Framework initialization details
- Agent and task creation logs
- Tool loading information
- Configuration details
- Execution flow information

Example debug output:
```
2024-01-11 10:30:45 - praisonai.cli - DEBUG - Logging configured with level: DEBUG
2024-01-11 10:30:45 - praisonai.agents_generator - DEBUG - Starting generate_crew_and_kickoff with framework: praisonai
2024-01-11 10:30:45 - praisonai.agents_generator - DEBUG - Current log level: DEBUG
2024-01-11 10:30:45 - praisonai.agents_generator - DEBUG - LOGLEVEL env var: DEBUG
```

## Troubleshooting

### No Debug Messages Appearing?

1. **Check the environment variable is set correctly:**
   ```bash
   echo $LOGLEVEL  # Should output: DEBUG
   ```

2. **Set the variable before importing PraisonAI:**
   ```python
   import os
   os.environ['LOGLEVEL'] = 'DEBUG'  # Set this first!
   from praisonai import PraisonAI   # Then import
   ```

3. **Use the test script to verify:**
   ```bash
   LOGLEVEL=DEBUG python test_simple_logging.py
   ```

### Framework-Specific Logging

Different frameworks may have their own logging:
- **CrewAI**: Set `verbose=True` in agent configuration
- **AutoGen**: Uses its own logging configuration
- **PraisonAI Agents**: Respects the LOGLEVEL setting

## Advanced Configuration

For more control over logging output:

```python
import logging
from rich.logging import RichHandler

# Custom logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True)]
)
```

## Best Practices

1. **Development**: Use `DEBUG` level during development
2. **Production**: Use `INFO` or `WARNING` level
3. **Testing**: Enable `DEBUG` to troubleshoot issues
4. **Performance**: Higher log levels (ERROR, CRITICAL) have less performance impact

## Related Files

- `src/praisonai/praisonai/cli.py` - Main logging configuration
- `src/praisonai/praisonai/agents_generator.py` - Agent-specific logging
- `src/praisonai-agents/praisonaiagents/main.py` - Rich logging configuration