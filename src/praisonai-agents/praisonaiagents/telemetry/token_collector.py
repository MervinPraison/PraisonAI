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
        """Calculate total tokens across all types."""
        return (
            self.input_tokens + 
            self.output_tokens + 
            self.cached_tokens + 
            self.reasoning_tokens +
            self.audio_input_tokens +
            self.audio_output_tokens
        )
    
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
    metrics_by_agent: Dict[str, TokenMetrics] = field(default_factory=dict)
    total_metrics: TokenMetrics = field(default_factory=TokenMetrics)
    
    def add_interaction(self, model: str, agent: Optional[str], metrics: TokenMetrics):
        """Add a new interaction's metrics."""
        self.total_interactions += 1
        
        # Update total metrics
        self.total_metrics = self.total_metrics + metrics
        
        # Update model-specific metrics
        if model not in self.metrics_by_model:
            self.metrics_by_model[model] = TokenMetrics()
        self.metrics_by_model[model] = self.metrics_by_model[model] + metrics
        
        # Update agent-specific metrics
        if agent:
            if agent not in self.metrics_by_agent:
                self.metrics_by_agent[agent] = TokenMetrics()
            self.metrics_by_agent[agent] = self.metrics_by_agent[agent] + metrics
    
    def get_summary(self) -> Dict:
        """Get a summary of session token usage."""
        return {
            "total_interactions": self.total_interactions,
            "total_tokens": self.total_metrics.total_tokens,
            "total_metrics": self.total_metrics.to_dict(),
            "by_model": {
                model: metrics.to_dict() 
                for model, metrics in self.metrics_by_model.items()
            },
            "by_agent": {
                agent: metrics.to_dict() 
                for agent, metrics in self.metrics_by_agent.items()
            }
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
    
    def track_tokens(
        self, 
        model: str, 
        agent: Optional[str], 
        metrics: TokenMetrics,
        metadata: Optional[Dict] = None
    ):
        """Track token usage for an interaction."""
        with self._lock:
            # Add to session metrics
            self._session_metrics.add_interaction(model, agent, metrics)
            
            # Track recent interaction
            interaction = {
                "timestamp": datetime.now().isoformat(),
                "model": model,
                "agent": agent,
                "metrics": metrics.to_dict(),
                "metadata": metadata or {}
            }
            
            self._recent_interactions.append(interaction)
            
            # Limit recent interactions
            if len(self._recent_interactions) > self._max_recent:
                self._recent_interactions.pop(0)
    
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