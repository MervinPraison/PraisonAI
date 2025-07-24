"""
Advanced metrics tracking for PraisonAI Agents.

This module provides comprehensive token and performance tracking
with session-level aggregation and export capabilities.
"""

import time
import json
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, List, Union
from datetime import datetime
from pathlib import Path

@dataclass
class TokenMetrics:
    """Comprehensive token tracking for all token types."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    # Special tokens
    audio_tokens: int = 0
    input_audio_tokens: int = 0
    output_audio_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    
    def __add__(self, other: 'TokenMetrics') -> 'TokenMetrics':
        """Enable metric aggregation."""
        return TokenMetrics(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            audio_tokens=self.audio_tokens + other.audio_tokens,
            input_audio_tokens=self.input_audio_tokens + other.input_audio_tokens,
            output_audio_tokens=self.output_audio_tokens + other.output_audio_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )
    
    def update_totals(self):
        """Update total_tokens based on input and output tokens."""
        self.total_tokens = self.input_tokens + self.output_tokens
    
    @classmethod
    def from_completion_usage(cls, usage: Any) -> 'TokenMetrics':
        """Create TokenMetrics from OpenAI CompletionUsage object."""
        metrics = cls()
        
        if hasattr(usage, 'prompt_tokens'):
            metrics.input_tokens = usage.prompt_tokens or 0
        if hasattr(usage, 'completion_tokens'):
            metrics.output_tokens = usage.completion_tokens or 0
        if hasattr(usage, 'total_tokens'):
            metrics.total_tokens = usage.total_tokens or 0
        
        # Handle audio tokens if present
        if hasattr(usage, 'prompt_tokens_details'):
            details = usage.prompt_tokens_details
            if hasattr(details, 'audio_tokens'):
                metrics.input_audio_tokens = details.audio_tokens or 0
                metrics.audio_tokens += metrics.input_audio_tokens
            if hasattr(details, 'cached_tokens'):
                metrics.cached_tokens = details.cached_tokens or 0
        
        if hasattr(usage, 'completion_tokens_details'):
            details = usage.completion_tokens_details
            if hasattr(details, 'audio_tokens'):
                metrics.output_audio_tokens = details.audio_tokens or 0
                metrics.audio_tokens += metrics.output_audio_tokens
            if hasattr(details, 'reasoning_tokens'):
                metrics.reasoning_tokens = details.reasoning_tokens or 0
        
        # Update total if not provided
        if metrics.total_tokens == 0:
            metrics.update_totals()
            
        return metrics

@dataclass
class PerformanceMetrics:
    """Performance tracking including TTFT and response times."""
    time_to_first_token: float = 0.0  # Time to first token in seconds
    total_time: float = 0.0  # Total generation time in seconds
    tokens_per_second: float = 0.0  # Tokens generated per second
    start_time: Optional[float] = None
    first_token_time: Optional[float] = None
    end_time: Optional[float] = None
    
    def start_timing(self):
        """Start timing for this request."""
        self.start_time = time.time()
    
    def mark_first_token(self):
        """Mark when first token was received."""
        if self.start_time:
            self.first_token_time = time.time()
            self.time_to_first_token = self.first_token_time - self.start_time
    
    def end_timing(self, token_count: int = 0):
        """End timing and calculate final metrics."""
        if self.start_time:
            self.end_time = time.time()
            self.total_time = self.end_time - self.start_time
            
            # Calculate tokens per second if we have token count
            if token_count > 0 and self.total_time > 0:
                self.tokens_per_second = token_count / self.total_time

class MetricsCollector:
    """Session-level metric aggregation and export."""
    
    def __init__(self):
        self.session_id = f"session_{int(time.time())}_{id(self)}"
        self.start_time = datetime.now()
        self.agent_metrics: Dict[str, TokenMetrics] = {}
        self.agent_performance: Dict[str, List[PerformanceMetrics]] = {}
        self.model_metrics: Dict[str, TokenMetrics] = {}
        self.total_metrics = TokenMetrics()
        
    def add_agent_metrics(self, agent_name: str, token_metrics: TokenMetrics, 
                         performance_metrics: Optional[PerformanceMetrics] = None,
                         model_name: Optional[str] = None):
        """Add metrics for a specific agent."""
        # Aggregate by agent
        if agent_name not in self.agent_metrics:
            self.agent_metrics[agent_name] = TokenMetrics()
        self.agent_metrics[agent_name] += token_metrics
        
        # Track performance metrics
        if performance_metrics:
            if agent_name not in self.agent_performance:
                self.agent_performance[agent_name] = []
            self.agent_performance[agent_name].append(performance_metrics)
        
        # Aggregate by model
        if model_name:
            if model_name not in self.model_metrics:
                self.model_metrics[model_name] = TokenMetrics()
            self.model_metrics[model_name] += token_metrics
        
        # Update total
        self.total_metrics += token_metrics
    
    def get_session_metrics(self) -> Dict[str, Any]:
        """Get aggregated session metrics."""
        # Calculate average performance metrics
        avg_performance = {}
        for agent_name, perf_list in self.agent_performance.items():
            if perf_list:
                avg_ttft = sum(p.time_to_first_token for p in perf_list) / len(perf_list)
                avg_total_time = sum(p.total_time for p in perf_list) / len(perf_list)
                avg_tps = sum(p.tokens_per_second for p in perf_list if p.tokens_per_second > 0)
                if avg_tps > 0:
                    avg_tps = avg_tps / len([p for p in perf_list if p.tokens_per_second > 0])
                
                avg_performance[agent_name] = {
                    "average_ttft": avg_ttft,
                    "average_total_time": avg_total_time,
                    "average_tokens_per_second": avg_tps,
                    "request_count": len(perf_list)
                }
        
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "duration_seconds": (datetime.now() - self.start_time).total_seconds(),
            "total_tokens": asdict(self.total_metrics),
            "by_agent": {name: asdict(metrics) for name, metrics in self.agent_metrics.items()},
            "by_model": {name: asdict(metrics) for name, metrics in self.model_metrics.items()},
            "performance": avg_performance
        }
    
    def export_metrics(self, file_path: Union[str, Path], format: str = "json"):
        """Export metrics to file."""
        metrics = self.get_session_metrics()
        
        file_path = Path(file_path)
        
        if format.lower() == "json":
            with open(file_path, 'w') as f:
                json.dump(metrics, f, indent=2, default=str)
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def reset(self):
        """Reset all metrics for a new session."""
        self.session_id = f"session_{int(time.time())}_{id(self)}"
        self.start_time = datetime.now()
        self.agent_metrics.clear()
        self.agent_performance.clear()
        self.model_metrics.clear()
        self.total_metrics = TokenMetrics()