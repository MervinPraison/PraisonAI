"""Backward-compat re-export — implementation lives in ``praisonai_bot.scheduler``."""

from praisonai._bootstrap import ensure_praisonai_bot

ensure_praisonai_bot()
from praisonai_bot.scheduler.executor import JobResult, ScheduledAgentExecutor

__all__ = ["ScheduledAgentExecutor", "JobResult"]
