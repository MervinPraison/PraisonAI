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


@runtime_checkable
class UsageQueryProtocol(Protocol):
    """Read path for token usage — UI dashboards and analytics."""

    def get_summary(self) -> Dict[str, Any]:
        """Aggregate totals and breakdowns by model/agent."""
        ...

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Recent usage records, newest last."""
        ...

    def get_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        ...

    def get_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        ...


class InMemoryUsageQuery:
    """Query adapter backed by InMemoryTokenUsageSink records."""

    def __init__(self, sink: InMemoryTokenUsageSink):
        self._sink = sink

    def get_summary(self) -> Dict[str, Any]:
        records = self._sink.records
        total_in = 0
        total_out = 0
        total_all = 0
        by_model: Dict[str, Dict[str, int]] = {}
        by_agent: Dict[str, Dict[str, int]] = {}
        
        # Single-pass optimization: calculate everything in one loop
        for r in records:
            r_in = r.get("input_tokens", 0)
            r_out = r.get("output_tokens", 0)
            r_total = r.get("total_tokens", r_in + r_out)
            
            total_in += r_in
            total_out += r_out
            total_all += r_total
            
            model = r.get("model", "unknown")
            agent = r.get("agent_name", "unknown")
            
            # Update by_model and by_agent efficiently
            for bucket, key in ((by_model, model), (by_agent, agent)):
                stats = bucket.setdefault(key, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
                stats["input_tokens"] += r_in
                stats["output_tokens"] += r_out
                stats["total_tokens"] += r_total
        return {
            "total_requests": len(records),
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_tokens": total_all,  # Use consistent calculation
            "by_model": by_model,
            "by_agent": by_agent,
        }

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._sink.records[-limit:]

    def get_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        return self._sink.get_by_task(task_id)

    def get_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        return self._sink.get_by_agent(agent_name)


class TokenCollectorUsageQuery:
    """Query adapter reading from the global TokenCollector + optional sink."""

    def __init__(self, collector: Any):
        self._collector = collector

    def get_summary(self) -> Dict[str, Any]:
        summary = self._collector.get_session_summary()
        return {
            "total_requests": summary.get("total_interactions", 0),
            "total_input_tokens": summary.get("total_metrics", {}).get("input_tokens", 0),
            "total_output_tokens": summary.get("total_metrics", {}).get("output_tokens", 0),
            "total_tokens": summary.get("total_tokens", 0),
            "by_model": summary.get("by_model", {}),
            "by_agent": summary.get("by_agent", {}),
        }

    def list_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._collector.get_recent_interactions(limit)

    def get_by_task(self, task_id: str) -> List[Dict[str, Any]]:
        sink = getattr(self._collector, "_sink", None)
        if sink and hasattr(sink, "get_by_task"):
            return sink.get_by_task(task_id)
        return []

    def get_by_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        sink = getattr(self._collector, "_sink", None)
        if sink and hasattr(sink, "get_by_agent"):
            return sink.get_by_agent(agent_name)
        return []
