"""
Token usage collector for tracking LLM token consumption.
Provides comprehensive tracking with minimal overhead.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from datetime import datetime
import threading
from collections import defaultdict


@dataclass
class TokenMetrics:
    """Represents token usage metrics for a single LLM interaction."""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    audio_input_tokens: int = 0
    audio_output_tokens: int = 0
    
    @property
    def total_tokens(self) -> int:
        """Calculate total tokens reported by the provider.

        cached_tokens are a subset of input_tokens, and reasoning_tokens /
        audio tokens are subsets of the input/output totals the provider
        already reports. Adding them again double-counts every cached prompt
        and o-series (reasoning) call, inflating usage by up to ~1.8x.
        """
        return self.input_tokens + self.output_tokens
    
    def to_dict(self) -> Dict[str, int]:
        """Convert to dictionary format."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "audio_input_tokens": self.audio_input_tokens,
            "audio_output_tokens": self.audio_output_tokens,
            "total_tokens": self.total_tokens
        }
    
    def __add__(self, other: 'TokenMetrics') -> 'TokenMetrics':
        """Add two TokenMetrics instances together."""
        if not isinstance(other, TokenMetrics):
            return NotImplemented
        
        return TokenMetrics(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            audio_input_tokens=self.audio_input_tokens + other.audio_input_tokens,
            audio_output_tokens=self.audio_output_tokens + other.audio_output_tokens
        )


@dataclass
class SessionTokenMetrics:
    """Aggregated token metrics for a session."""
    total_interactions: int = 0
    metrics_by_model: Dict[str, TokenMetrics] = field(default_factory=dict)
    # Aggregated per agent *identity* (a stable per-instance key such as an
    # Agent's ``_approval_scope_id``), not the bare display name. Two unrelated
    # agents that happen to share a name (e.g. the default ``"Agent"``) must not
    # merge into one cost bucket, which would make per-tenant accounting
    # unrecoverable. Each entry carries the display name for reporting.
    metrics_by_agent_id: Dict[str, Dict] = field(default_factory=dict)
    total_metrics: TokenMetrics = field(default_factory=TokenMetrics)
    
    def add_interaction(
        self,
        model: str,
        agent: Optional[str],
        metrics: TokenMetrics,
        agent_id: Optional[str] = None,
    ):
        """Add a new interaction's metrics.

        ``agent`` is the display name; ``agent_id`` is a stable per-instance
        identity used as the aggregation key so name collisions between
        unrelated agents never merge their usage. When ``agent_id`` is omitted
        the display name is used as the key (backward-compatible fallback).
        """
        self.total_interactions += 1
        
        # Update total metrics
        self.total_metrics = self.total_metrics + metrics
        
        # Update model-specific metrics
        if model not in self.metrics_by_model:
            self.metrics_by_model[model] = TokenMetrics()
        self.metrics_by_model[model] = self.metrics_by_model[model] + metrics
        
        # Update agent-specific metrics, keyed by identity (not display name).
        key = agent_id or agent
        if key:
            bucket = self.metrics_by_agent_id.get(key)
            if bucket is None:
                bucket = {"name": agent, "metrics": TokenMetrics()}
                self.metrics_by_agent_id[key] = bucket
            bucket["metrics"] = bucket["metrics"] + metrics
    
    def get_summary(self) -> Dict:
        """Get a summary of session token usage.

        ``by_agent`` is keyed by display name for readability (metrics for
        same-named agents are summed only for display); ``by_agent_id`` keeps
        the collision-free per-identity breakdown that callers use to scope
        usage to a specific instance/tenant.
        """
        by_agent: Dict[str, TokenMetrics] = {}
        by_agent_id: Dict[str, Dict] = {}
        for key, bucket in self.metrics_by_agent_id.items():
            name = bucket.get("name") or key
            agent_metrics = bucket["metrics"]
            if name in by_agent:
                by_agent[name] = by_agent[name] + agent_metrics
            else:
                by_agent[name] = agent_metrics
            by_agent_id[key] = {"name": name, "metrics": agent_metrics.to_dict()}
        return {
            "total_interactions": self.total_interactions,
            "total_tokens": self.total_metrics.total_tokens,
            "total_metrics": self.total_metrics.to_dict(),
            "by_model": {
                model: metrics.to_dict() 
                for model, metrics in self.metrics_by_model.items()
            },
            "by_agent": {
                name: metrics.to_dict()
                for name, metrics in by_agent.items()
            },
            "by_agent_id": by_agent_id,
        }


class TokenCollector:
    """
    Global token collector for tracking token usage across the application.
    Thread-safe implementation for concurrent access.
    """
    
    def __init__(self):
        self._lock = threading.Lock()
        self._session_metrics = SessionTokenMetrics()
        self._recent_interactions: List[Dict] = []
        self._max_recent = 100
        self._sink = None  # Optional TokenUsageSinkProtocol

    def set_sink(self, sink) -> None:
        """Set a token usage sink for persistence.
        
        Args:
            sink: Any object implementing TokenUsageSinkProtocol
                  (must have a persist() method)
        """
        self._sink = sink
    
    def track_tokens(
        self, 
        model: str, 
        agent: Optional[str], 
        metrics: TokenMetrics,
        metadata: Optional[Dict] = None,
        agent_id: Optional[str] = None,
    ):
        """Track token usage for an interaction.

        ``agent`` is the display name; ``agent_id`` is an optional stable
        per-instance identity used as the aggregation key so unrelated agents
        that share a name never merge into one cost bucket.
        """
        with self._lock:
            # Add to session metrics
            self._session_metrics.add_interaction(model, agent, metrics, agent_id=agent_id)
            
            # Track recent interaction
            interaction = {
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "agent": agent,
                "agent_id": agent_id,
                "metrics": metrics.to_dict(),
                "metadata": metadata or {}
            }
            
            self._recent_interactions.append(interaction)
            
            # Limit recent interactions
            if len(self._recent_interactions) > self._max_recent:
                self._recent_interactions.pop(0)
        
        # Call sink outside the lock to avoid holding it during I/O
        if self._sink is not None:
            try:
                task_id = (metadata or {}).get("task_id", "")
                self._sink.persist(
                    task_id=task_id,
                    agent_name=agent or "",
                    model=model,
                    metrics=metrics,
                    metadata=metadata,
                )
            except Exception:
                pass  # Sink errors must not break token tracking
    
    def get_session_summary(self) -> Dict:
        """Get summary of token usage for the session."""
        with self._lock:
            return self._session_metrics.get_summary()
    
    def get_recent_interactions(self, limit: int = 10) -> List[Dict]:
        """Get recent interactions with token metrics."""
        with self._lock:
            return self._recent_interactions[-limit:]
    
    def reset(self):
        """Reset all collected metrics."""
        with self._lock:
            self._session_metrics = SessionTokenMetrics()
            self._recent_interactions.clear()
    
    def export_metrics(self) -> Dict:
        """Export all metrics for external use."""
        with self._lock:
            return {
                "session": self._session_metrics.get_summary(),
                "recent_interactions": self._recent_interactions.copy()
            }


# Global token collector instance
_token_collector = TokenCollector()


def get_token_collector() -> TokenCollector:
    """Return the global TokenCollector singleton."""
    return _token_collector