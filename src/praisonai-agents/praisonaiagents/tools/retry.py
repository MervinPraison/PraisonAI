"""Retry policy and fallback configuration for tools."""
import random
from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class RetryPolicy:
    """Configuration for tool retry behavior with exponential backoff and jitter.
    
    Example:
        policy = RetryPolicy(
            max_attempts=3,
            backoff_factor=2.0,
            retry_on={"timeout", "rate_limit"}
        )
        
        # With jitter for production use
        policy = RetryPolicy(jitter=True, jitter_factor=0.25)
    """
    max_attempts: int = 3
    backoff_factor: float = 2.0
    initial_delay_ms: int = 1000
    max_delay_ms: int = 30000
    retry_on: Set[str] = field(default_factory=lambda: {"timeout", "rate_limit", "connection_error"})
    jitter: bool = False
    jitter_factor: float = 0.25  # ±25% randomization
    
    def __post_init__(self):
        """Validate configuration values."""
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.backoff_factor < 1.0:
            raise ValueError("backoff_factor must be >= 1.0")
        if self.initial_delay_ms < 0:
            raise ValueError("initial_delay_ms must be >= 0")
        if self.max_delay_ms < self.initial_delay_ms:
            raise ValueError("max_delay_ms must be >= initial_delay_ms")
        if not 0.0 <= self.jitter_factor <= 1.0:
            raise ValueError("jitter_factor must be between 0.0 and 1.0")
    
    def should_retry(self, error_type: str, attempt: int) -> bool:
        """Check if should retry given error type and attempt number."""
        if attempt >= self.max_attempts:
            return False
        return error_type in self.retry_on
    
    def get_delay_ms(self, attempt: int) -> int:
        """Calculate delay for given attempt (exponential backoff with optional jitter)."""
        delay = self.initial_delay_ms * (self.backoff_factor ** attempt)
        delay = min(delay, self.max_delay_ms)
        
        if self.jitter:
            # Add random jitter: delay * (1 ± jitter_factor)
            jitter_range = delay * self.jitter_factor
            delay = delay + random.uniform(-jitter_range, jitter_range)
            delay = max(0, delay)  # Ensure non-negative
        
        return int(delay)


@dataclass
class FallbackChain:
    """Chain of fallback tools to try if primary fails.
    
    Example:
        chain = FallbackChain(
            tools=["web_search", "cached_search", "default_response"]
        )
    """
    tools: List[str] = field(default_factory=list)
    stop_on_success: bool = True
    
    def __iter__(self):
        return iter(self.tools)
    
    def __len__(self) -> int:
        return len(self.tools)


@dataclass
class ToolExecutionConfig:
    """Combined execution configuration for a tool."""
    retry_policy: Optional[RetryPolicy] = None
    fallback_chain: Optional[FallbackChain] = None
    timeout_ms: Optional[int] = None
    
    @classmethod
    def default(cls) -> "ToolExecutionConfig":
        return cls(retry_policy=RetryPolicy())
