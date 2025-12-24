"""
Thinking Tracker for PraisonAI Agents.

Tracks thinking usage and provides reporting.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime


@dataclass
class ThinkingUsage:
    """Usage statistics for a single thinking session."""
    tokens_used: int = 0
    time_seconds: float = 0.0
    budget_tokens: int = 0
    budget_time: Optional[float] = None
    complexity: float = 0.5
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    
    @property
    def tokens_remaining(self) -> int:
        """Get remaining token budget."""
        return max(0, self.budget_tokens - self.tokens_used)
    
    @property
    def time_remaining(self) -> Optional[float]:
        """Get remaining time budget."""
        if self.budget_time is None:
            return None
        return max(0.0, self.budget_time - self.time_seconds)
    
    @property
    def token_utilization(self) -> float:
        """Get token utilization percentage."""
        if self.budget_tokens == 0:
            return 0.0
        return self.tokens_used / self.budget_tokens
    
    @property
    def is_over_budget(self) -> bool:
        """Check if over token budget."""
        return self.tokens_used > self.budget_tokens
    
    @property
    def is_over_time(self) -> bool:
        """Check if over time budget."""
        if self.budget_time is None:
            return False
        return self.time_seconds > self.budget_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tokens_used": self.tokens_used,
            "time_seconds": self.time_seconds,
            "budget_tokens": self.budget_tokens,
            "budget_time": self.budget_time,
            "complexity": self.complexity,
            "tokens_remaining": self.tokens_remaining,
            "token_utilization": self.token_utilization,
            "is_over_budget": self.is_over_budget
        }


@dataclass
class ThinkingTracker:
    """
    Tracks thinking usage across multiple sessions.
    
    Provides aggregate statistics and reporting.
    """
    sessions: List[ThinkingUsage] = field(default_factory=list)
    total_tokens_used: int = 0
    total_time_seconds: float = 0.0
    
    def start_session(
        self,
        budget_tokens: int,
        budget_time: Optional[float] = None,
        complexity: float = 0.5
    ) -> ThinkingUsage:
        """
        Start a new thinking session.
        
        Args:
            budget_tokens: Token budget for this session
            budget_time: Optional time budget
            complexity: Task complexity (0.0 to 1.0)
            
        Returns:
            ThinkingUsage for tracking
        """
        usage = ThinkingUsage(
            budget_tokens=budget_tokens,
            budget_time=budget_time,
            complexity=complexity,
            started_at=datetime.now()
        )
        self.sessions.append(usage)
        return usage
    
    def end_session(
        self,
        usage: ThinkingUsage,
        tokens_used: int,
        time_seconds: float
    ):
        """
        End a thinking session.
        
        Args:
            usage: The usage object from start_session
            tokens_used: Actual tokens used
            time_seconds: Actual time taken
        """
        usage.tokens_used = tokens_used
        usage.time_seconds = time_seconds
        usage.ended_at = datetime.now()
        
        self.total_tokens_used += tokens_used
        self.total_time_seconds += time_seconds
    
    @property
    def session_count(self) -> int:
        """Get number of sessions."""
        return len(self.sessions)
    
    @property
    def average_tokens_per_session(self) -> float:
        """Get average tokens per session."""
        if not self.sessions:
            return 0.0
        return self.total_tokens_used / len(self.sessions)
    
    @property
    def average_time_per_session(self) -> float:
        """Get average time per session."""
        if not self.sessions:
            return 0.0
        return self.total_time_seconds / len(self.sessions)
    
    @property
    def average_utilization(self) -> float:
        """Get average budget utilization."""
        if not self.sessions:
            return 0.0
        return sum(s.token_utilization for s in self.sessions) / len(self.sessions)
    
    @property
    def over_budget_count(self) -> int:
        """Get number of sessions that went over budget."""
        return sum(1 for s in self.sessions if s.is_over_budget)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        return {
            "session_count": self.session_count,
            "total_tokens_used": self.total_tokens_used,
            "total_time_seconds": self.total_time_seconds,
            "average_tokens_per_session": self.average_tokens_per_session,
            "average_time_per_session": self.average_time_per_session,
            "average_utilization": self.average_utilization,
            "over_budget_count": self.over_budget_count
        }
    
    def clear(self):
        """Clear all tracking data."""
        self.sessions.clear()
        self.total_tokens_used = 0
        self.total_time_seconds = 0.0
