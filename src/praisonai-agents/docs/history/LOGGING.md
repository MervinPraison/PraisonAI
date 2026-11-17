# Centralized Logging in PraisonAI Agents

This document explains the enhanced centralized logging system implemented to address inconsistent logging patterns across the codebase.

## Problem Addressed

- **53+ scattered logger instances** with no unified configuration
- **No standard log format** across modules  
- **Mixed logging approaches** (logger.debug(), print(), console.print())
- **No structured logging option** for production deployments
- **Difficult filtering** by subsystem in multi-agent runs

## Solution

Enhanced the existing `praisonaiagents/_logging.py` with:

1. **Consistent naming convention**: All loggers follow `praisonaiagents.<module>` pattern
2. **Structured logging support**: JSON output for production environments
3. **Backward compatibility**: Existing code continues to work
4. **Centralized configuration**: Single place to configure all logging
5. **Optional extra data**: Structured data for better observability

## Quick Start

### Basic Usage

```python
# New recommended approach
from praisonaiagents import get_logger

# Automatic module detection
logger = get_logger()
logger.info("This is a log message")

# Explicit module name
logger = get_logger(__name__)
logger.info("Explicit module logging")
```

### Structured Logging

```python
import os
from praisonaiagents import get_logger, configure_structured_logging

# Enable structured JSON logging
os.environ['PRAISONAI_STRUCTURED_LOGS'] = 'true'
configure_structured_logging()

# Logger with extra structured data
logger = get_logger(extra_data={"agent_id": "assistant", "session": "123"})
logger.info("Task completed", extra={"task_id": "task_001", "duration": 1.5})
```

Output:
```json
{
  "timestamp": "2026-03-30T21:35:00Z",
  "level": "INFO", 
  "logger": "praisonaiagents.agent.agent",
  "message": "Task completed",
  "module": "agent",
  "function": "start",
  "line": 42,
  "agent_id": "assistant",
  "session": "123",
  "task_id": "task_001",
  "duration": 1.5
}
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LOGLEVEL` | `WARNING` | Global log level (DEBUG, INFO, WARNING, ERROR) |
| `PRAISONAI_STRUCTURED_LOGS` | `false` | Enable JSON structured logging |

### Per-Module Configuration

```bash
# Set specific module to DEBUG level
export LOGLEVEL=INFO
# Configure in Python:
logging.getLogger('praisonaiagents.memory').setLevel(logging.DEBUG)
```

## Migration Guide

### For New Code

Use the new logging utilities:

```python
# ✅ Recommended - new code
from praisonaiagents import get_logger
logger = get_logger()
```

### For Existing Code

**No changes required** - existing code continues to work:

```python
# ✅ Still works - existing code
import logging
logger = logging.getLogger(__name__)
```

**Optional enhancement** for better observability:

```python
# ✅ Enhanced - gradually migrate
from praisonaiagents._logging import get_logger
logger = get_logger(__name__, extra_data={"subsystem": "agent"})
```

## Naming Convention

The `get_logger()` function automatically ensures consistent naming:

| Input | Output Logger Name |
|-------|--------------------|
| `"my_module"` | `"praisonaiagents.my_module"` |
| `"praisonaiagents.existing"` | `"praisonaiagents.existing"` (unchanged) |
| `"praisonai.other"` | `"praisonaiagents.other"` |
| `"__main__"` | `"praisonaiagents.main"` |
| `None` (auto-detect) | `"praisonaiagents.<current_module>"` |

## Production Deployment

### ELK Stack / Elasticsearch

```python
import os
from praisonaiagents import configure_structured_logging

# Enable JSON logging for log shipping
os.environ['PRAISONAI_STRUCTURED_LOGS'] = 'true'
configure_structured_logging()
```

### CloudWatch / Splunk

```python
import logging
from praisonaiagents import get_logger, StructuredFormatter

# Custom handler with structured format
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())

logger = get_logger()
logger.addHandler(handler)
```

### Filtering by Subsystem

With structured logging enabled, you can easily filter logs:

```bash
# Filter by agent subsystem
jq 'select(.logger | startswith("praisonaiagents.agent"))' logs.json

# Filter by specific agent
jq 'select(.agent_id == "assistant")' logs.json

# Filter by session
jq 'select(.session == "session_123")' logs.json
```

## Backward Compatibility

- ✅ All existing `logging.getLogger(__name__)` calls continue to work
- ✅ No performance impact on existing code
- ✅ No breaking changes to public APIs
- ✅ Gradual migration path available

## Examples

See the updated modules for examples:
- `praisonaiagents/plugins/builtin/logging_plugin.py` - Logging plugin with extra data
- `praisonaiagents/memory/memory.py` - Memory module with subsystem tagging

## Benefits

1. **Unified format**: All PraisonAI logs follow the same format
2. **Better observability**: Structured data for monitoring and debugging  
3. **Easy filtering**: Filter by subsystem, agent, or session
4. **Production ready**: JSON output for log aggregation systems
5. **Zero breaking changes**: Existing code continues to work unchanged
6. **Performance conscious**: No import-time overhead for normal usage