"""
PraisonAI Agents Metrics Module

This module provides comprehensive metrics tracking for agents including:
- Token usage (input, output, audio, cached, reasoning tokens)
- Performance metrics (TTFT, response time, tokens per second)
- Session-level aggregation
- Export functionality
"""

import time
import json
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

# Import existing token classes for compatibility
from .llm.openai_client import CompletionUsage, CompletionTokensDetails, PromptTokensDetails


@dataclass
class TokenMetrics:
    """
    Comprehensive token tracking compatible with existing CompletionUsage.
    
    This class extends the functionality of CompletionUsage while maintaining
    backward compatibility with existing OpenAI response structures.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    # Special tokens (from OpenAI spec)
    audio_tokens: int = 0
    input_audio_tokens: int = 0
    output_audio_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    
    # Additional metadata
    model: Optional[str] = None
    timestamp: Optional[datetime] = field(default_factory=datetime.now)
    
    @classmethod
    def from_completion_usage(cls, usage: CompletionUsage, model: Optional[str] = None) -> 'TokenMetrics':
        """
        Create TokenMetrics from existing CompletionUsage object.
        
        Args:
            usage: CompletionUsage object from LLM response
            model: Model name for metadata
            
        Returns:
            TokenMetrics instance
        """
        metrics = cls(
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            model=model
        )
        
        # Extract detailed token information
        if usage.completion_tokens_details:
            details = usage.completion_tokens_details
            metrics.audio_tokens = details.audio_tokens or 0
            metrics.output_audio_tokens = details.audio_tokens or 0
            metrics.reasoning_tokens = details.reasoning_tokens or 0
        
        if usage.prompt_tokens_details:
            details = usage.prompt_tokens_details
            metrics.input_audio_tokens = details.audio_tokens or 0
            metrics.cached_tokens = details.cached_tokens or 0
        
        # Handle cache tokens from root level
        if hasattr(usage, 'prompt_cache_hit_tokens'):
            metrics.cached_tokens += usage.prompt_cache_hit_tokens
        
        return metrics
    
    def __add__(self, other: 'TokenMetrics') -> 'TokenMetrics':
        """Enable metric aggregation with + operator."""
        if not isinstance(other, TokenMetrics):
            raise TypeError(f"Cannot add TokenMetrics with {type(other)}")
        
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
            model=self.model,  # Keep original model name
            timestamp=self.timestamp  # Keep original timestamp
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        if result['timestamp']:
            result['timestamp'] = result['timestamp'].isoformat()
        return result


@dataclass
class PerformanceMetrics:
    """
    Performance tracking including Time-to-First-Token (TTFT) and response metrics.
    """
    time_to_first_token: Optional[float] = None  # TTFT in seconds
    total_time: float = 0.0  # Total response time in seconds
    tokens_per_second: Optional[float] = None  # Generation speed
    
    # Additional timing metrics
    start_time: Optional[float] = None
    first_token_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # Context
    model: Optional[str] = None
    streaming: bool = False
    timestamp: Optional[datetime] = field(default_factory=datetime.now)
    
    def start_tracking(self) -> None:
        """Start performance tracking."""
        self.start_time = time.time()
    
    def mark_first_token(self) -> None:
        """Mark when first token was received."""
        if self.start_time is not None:
            self.first_token_time = time.time()
            self.time_to_first_token = self.first_token_time - self.start_time
    
    def end_tracking(self, token_count: Optional[int] = None) -> None:
        """
        End performance tracking and calculate final metrics.
        
        Args:
            token_count: Number of tokens generated for TPS calculation
        """
        if self.start_time is not None:
            self.end_time = time.time()
            self.total_time = self.end_time - self.start_time
            
            # Calculate tokens per second if token count provided
            if token_count is not None and self.total_time > 0:
                self.tokens_per_second = token_count / self.total_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        if result['timestamp']:
            result['timestamp'] = result['timestamp'].isoformat()
        return result


@dataclass
class SessionMetrics:
    """
    Session-level aggregated metrics.
    """
    total_tokens: TokenMetrics = field(default_factory=TokenMetrics)
    total_requests: int = 0
    total_time: float = 0.0
    average_response_time: float = 0.0
    
    # Per-agent breakdown
    by_agent: Dict[str, TokenMetrics] = field(default_factory=dict)
    
    # Per-model breakdown
    by_model: Dict[str, TokenMetrics] = field(default_factory=dict)
    
    # Session metadata
    session_id: Optional[str] = None
    start_time: Optional[datetime] = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    
    def add_request_metrics(
        self, 
        token_metrics: TokenMetrics, 
        performance_metrics: PerformanceMetrics,
        agent_name: Optional[str] = None
    ) -> None:
        """
        Add metrics from a single request to session totals.
        
        Args:
            token_metrics: Token usage for this request
            performance_metrics: Performance data for this request
            agent_name: Name of agent that made the request
        """
        # Add to totals
        self.total_tokens = self.total_tokens + token_metrics
        self.total_requests += 1
        self.total_time += performance_metrics.total_time
        
        # Update average response time
        if self.total_requests > 0:
            self.average_response_time = self.total_time / self.total_requests
        
        # Track by agent
        if agent_name:
            if agent_name not in self.by_agent:
                self.by_agent[agent_name] = TokenMetrics()
            self.by_agent[agent_name] = self.by_agent[agent_name] + token_metrics
        
        # Track by model
        if token_metrics.model:
            if token_metrics.model not in self.by_model:
                self.by_model[token_metrics.model] = TokenMetrics()
            self.by_model[token_metrics.model] = self.by_model[token_metrics.model] + token_metrics
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = {
            'total_tokens': self.total_tokens.to_dict(),
            'total_requests': self.total_requests,
            'total_time': self.total_time,
            'average_response_time': self.average_response_time,
            'by_agent': {name: metrics.to_dict() for name, metrics in self.by_agent.items()},
            'by_model': {model: metrics.to_dict() for model, metrics in self.by_model.items()},
            'session_id': self.session_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'end_time': self.end_time.isoformat() if self.end_time else None
        }
        return result


class MetricsCollector:
    """
    Session-level metrics collector with aggregation and export capabilities.
    """
    
    def __init__(self, session_id: Optional[str] = None):
        """
        Initialize metrics collector.
        
        Args:
            session_id: Optional session identifier
        """
        self.session_id = session_id or f"session_{int(time.time())}"
        self.session_metrics = SessionMetrics(session_id=self.session_id)
        self._request_history: List[Dict[str, Any]] = []
    
    def track_request(
        self,
        token_metrics: TokenMetrics,
        performance_metrics: PerformanceMetrics,
        agent_name: Optional[str] = None,
        request_id: Optional[str] = None
    ) -> None:
        """
        Track a single request with full metrics.
        
        Args:
            token_metrics: Token usage for this request
            performance_metrics: Performance data for this request
            agent_name: Name of agent that made the request
            request_id: Optional request identifier
        """
        # Add to session aggregation
        self.session_metrics.add_request_metrics(token_metrics, performance_metrics, agent_name)
        
        # Store individual request for detailed history
        request_data = {
            'request_id': request_id or f"req_{len(self._request_history)}",
            'agent_name': agent_name,
            'token_metrics': token_metrics.to_dict(),
            'performance_metrics': performance_metrics.to_dict(),
            'timestamp': datetime.now().isoformat()
        }
        self._request_history.append(request_data)
    
    def get_session_metrics(self) -> SessionMetrics:
        """Get current session-level aggregated metrics."""
        return self.session_metrics
    
    def get_agent_metrics(self, agent_name: str) -> Optional[TokenMetrics]:
        """Get aggregated metrics for a specific agent."""
        return self.session_metrics.by_agent.get(agent_name)
    
    def get_model_metrics(self, model: str) -> Optional[TokenMetrics]:
        """Get aggregated metrics for a specific model."""
        return self.session_metrics.by_model.get(model)
    
    def export_metrics(self, file_path: Union[str, Path]) -> None:
        """
        Export metrics to JSON file.
        
        Args:
            file_path: Path to save the metrics file
        """
        file_path = Path(file_path)
        
        export_data = {
            'session_metrics': self.session_metrics.to_dict(),
            'request_history': self._request_history,
            'export_timestamp': datetime.now().isoformat(),
            'version': '1.0'
        }
        
        with open(file_path, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
    
    def export_to_opentelemetry(self) -> Dict[str, Any]:
        """
        Export metrics in OpenTelemetry format.
        
        Returns:
            Dictionary with OpenTelemetry-compatible metrics
        """
        # This would integrate with OpenTelemetry SDK
        # For now, return a simplified format
        return {
            'resource': {
                'service.name': 'praisonai-agents',
                'service.version': '1.0',
                'session.id': self.session_id
            },
            'metrics': [
                {
                    'name': 'praisonai.tokens.total',
                    'value': self.session_metrics.total_tokens.total_tokens,
                    'unit': 'tokens',
                    'attributes': {
                        'session.id': self.session_id
                    }
                },
                {
                    'name': 'praisonai.requests.total',
                    'value': self.session_metrics.total_requests,
                    'unit': 'requests',
                    'attributes': {
                        'session.id': self.session_id
                    }
                },
                {
                    'name': 'praisonai.response_time.average',
                    'value': self.session_metrics.average_response_time,
                    'unit': 'seconds',
                    'attributes': {
                        'session.id': self.session_id
                    }
                }
            ]
        }
    
    def clear_metrics(self) -> None:
        """Clear all collected metrics."""
        self.session_metrics = SessionMetrics(session_id=self.session_id)
        self._request_history.clear()


# Utility functions for easy access
def create_token_metrics_from_response(response, model: Optional[str] = None) -> Optional[TokenMetrics]:
    """
    Create TokenMetrics from any LLM response that has usage information.
    
    Args:
        response: LLM response object with usage attribute
        model: Model name for metadata
        
    Returns:
        TokenMetrics instance or None if no usage info
    """
    if hasattr(response, 'usage') and response.usage:
        return TokenMetrics.from_completion_usage(response.usage, model)
    return None


def create_performance_metrics(
    start_time: float,
    first_token_time: Optional[float] = None,
    end_time: Optional[float] = None,
    token_count: Optional[int] = None,
    model: Optional[str] = None,
    streaming: bool = False
) -> PerformanceMetrics:
    """
    Create PerformanceMetrics from timing data.
    
    Args:
        start_time: Request start timestamp
        first_token_time: First token received timestamp
        end_time: Request completion timestamp
        token_count: Number of tokens generated
        model: Model name for metadata
        streaming: Whether response was streamed
        
    Returns:
        PerformanceMetrics instance
    """
    metrics = PerformanceMetrics(
        start_time=start_time,
        first_token_time=first_token_time,
        end_time=end_time,
        model=model,
        streaming=streaming
    )
    
    # Calculate TTFT
    if first_token_time and start_time:
        metrics.time_to_first_token = first_token_time - start_time
    
    # Calculate total time and TPS
    if end_time and start_time:
        metrics.total_time = end_time - start_time
        if token_count and metrics.total_time > 0:
            metrics.tokens_per_second = token_count / metrics.total_time
    
    return metrics