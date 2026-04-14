"""Token Usage Sink Protocols for PraisonAI Agents.

Provides pluggable persistence for per-task token usage data.
Matches Multica's task_usage table pattern but as a protocol,
so users can plug in any backend (DB, file, API, etc.).

Usage:
    from praisonaiagents.telemetry.protocols import InMemoryTokenUsageSink
    from praisonaiagents.telemetry.token_collector import TokenCollector
    
    sink = InMemoryTokenUsageSink()
    collector = TokenCollector()
    collector.set_sink(sink)
"""

from typing import Protocol, runtime_checkable, List, Dict, Any, Optional
from datetime import datetime


@runtime_checkable
class TokenUsageSinkProtocol(Protocol):
    """Protocol for persisting token usage data.
    
    Implementations can write to databases, files, APIs, etc.
    The NoOp implementation is used by default for zero overhead.
    """

    def persist(
        self,
        task_id: str,
        agent_name: str,
        model: str,
        metrics: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Persist token usage for a task execution.
        
        Args:
            task_id: Task identifier
            agent_name: Agent that consumed tokens
            model: LLM model name
            metrics: TokenMetrics instance
            metadata: Optional extra metadata
        """
        ...


class NoOpTokenUsageSink:
    """Default sink that does nothing. Zero overhead."""

    def persist(
        self,
        task_id: str,
        agent_name: str,
        model: str,
        metrics: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        pass


class InMemoryTokenUsageSink:
    """In-memory sink for testing and debugging.
    
    Stores all usage records in a list for inspection.
    """

    def __init__(self):
        self.records: List[Dict[str, Any]] = []

    def persist(
        self,
        task_id: str,
        agent_name: str,
        model: str,
        metrics: Any,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = {
            "task_id": task_id,
            "agent_name": agent_name,
            "model": model,
            "input_tokens": getattr(metrics, "input_tokens", 0),
            "output_tokens": getattr(metrics, "output_tokens", 0),
            "cached_tokens": getattr(metrics, "cached_tokens", 0),
            "total_tokens": getattr(metrics, "total_tokens", 0),
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }
        self.records.append(record)

    def get_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all records for a specific task."""
        return [r for r in self.records if r["task_id"] == task_id]

    def get_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """Get all records for a specific agent."""
        return [r for r in self.records if r["agent_name"] == agent_name]

    def clear(self) -> None:
        """Clear all records."""
        self.records.clear()
