"""Backward-compatible re-export. Prefer `praisonai.scheduler`.

This module is deprecated. Use the canonical implementation in the
scheduler package for full functionality including YAML and recipe support.
"""

import warnings

warnings.warn(
    "praisonai.agent_scheduler is deprecated; "
    "use 'from praisonai.scheduler import AgentScheduler' instead.",
    DeprecationWarning, stacklevel=2,
)

from praisonai.scheduler.agent_scheduler import (  # noqa: F401
    AgentScheduler, PraisonAgentExecutor, AgentExecutorInterface,
    create_agent_scheduler
)