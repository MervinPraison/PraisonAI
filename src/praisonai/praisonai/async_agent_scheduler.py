"""Backward-compatible re-export. Prefer `praisonai.scheduler`.

This module is deprecated. Use the canonical implementation in the
scheduler package for full functionality including async support.
"""

import warnings

warnings.warn(
    "praisonai.async_agent_scheduler is deprecated; "
    "use 'from praisonai.scheduler import AsyncAgentScheduler' instead.",
    DeprecationWarning, 
    stacklevel=2,
)

# Re-export from the canonical location
from .scheduler.async_agent_scheduler import (  # noqa: F401
    AsyncAgentScheduler, 
    AsyncPraisonAgentExecutor, 
    AsyncAgentExecutorInterface,
    create_async_agent_scheduler,
    logger,
)
