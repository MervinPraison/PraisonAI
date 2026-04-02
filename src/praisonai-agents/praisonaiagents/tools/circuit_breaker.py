"""Circuit breaker pattern for external service calls.

Implements the circuit breaker pattern to prevent cascading failures when external services
(DB, LLM, MCP) are down. Integrates with existing retry utilities in tools/retry.py.

Following the protocol-driven architecture from AGENTS.md.
"""

import asyncio
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable, Union
from concurrent.futures import Future


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failures detected, calls rejected
    HALF_OPEN = "half_open"  # Recovery probe mode


@dataclass 
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior.
    
    Attributes:
        failure_threshold: Number of failures to open circuit
        recovery_timeout: Time (seconds) to wait before transitioning to half-open
        success_threshold: Number of successes in half-open to close circuit
        timeout: Service call timeout (seconds)
        monitor_window: Time window for failure rate calculation (seconds)
        enable_health_check: Whether to perform periodic health checks
        health_check_interval: Interval between health checks (seconds)
        graceful_degradation: Whether to enable graceful degradation
    """
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    timeout: float = 30.0
    monitor_window: float = 300.0  # 5 minutes
    enable_health_check: bool = True
    health_check_interval: float = 30.0
    graceful_degradation: bool = True


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics and state information."""
    state: CircuitState
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_requests: int = 0
    rejected_requests: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary for telemetry."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "total_requests": self.total_requests,
            "rejected_requests": self.rejected_requests,
        }


@runtime_checkable
class CircuitBreakerProtocol(Protocol):
    """Protocol for circuit breaker implementations."""
    
    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        ...
    
    @property
    def stats(self) -> CircuitBreakerStats:
        """Current statistics."""
        ...
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        ...
    
    async def acall(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker protection."""
        ...
    
    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        ...


@runtime_checkable
class HealthCheckProtocol(Protocol):
    """Protocol for health check implementations."""
    
    def health_check(self) -> bool:
        """Perform health check. Return True if service is healthy."""
        ...
    
    async def ahealth_check(self) -> bool:
        """Perform async health check. Return True if service is healthy."""
        ...


class CircuitBreakerException(Exception):
    """Raised when circuit breaker is open and calls are rejected."""
    
    def __init__(self, service_name: str, state: CircuitState):
        self.service_name = service_name
        self.state = state
        super().__init__(f"Circuit breaker open for service '{service_name}', state: {state.value}")


class CircuitBreaker:
    """Lightweight circuit breaker implementation.
    
    Provides circuit breaker functionality with health monitoring and graceful degradation.
    Thread-safe and async-safe implementation.
    
    Example:
        # Basic usage
        breaker = CircuitBreaker("database")
        
        try:
            result = breaker.call(db_query, "SELECT * FROM users")
        except CircuitBreakerException:
            # Handle circuit open - use cache or fallback
            result = get_cached_users()
        
        # Async usage
        result = await breaker.acall(async_db_query, "SELECT * FROM users")
        
        # With health check
        def db_health_check():
            return ping_database()
        
        breaker = CircuitBreaker("database", health_check=db_health_check)
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        health_check: Optional[Union[Callable[[], bool], HealthCheckProtocol]] = None,
        fallback: Optional[Callable] = None,
    ):
        """Initialize circuit breaker.
        
        Args:
            name: Service name for identification
            config: Configuration settings
            health_check: Health check function or protocol
            fallback: Fallback function for graceful degradation
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._health_check = health_check
        self._fallback = fallback
        
        # State management (thread-safe)
        self._lock = threading.RLock()
        self._stats = CircuitBreakerStats(state=CircuitState.CLOSED)
        self._failure_times: List[float] = []
        self._health_check_task: Optional[asyncio.Task] = None
        self._last_health_check: Optional[float] = None
    
    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        with self._lock:
            return self._stats.state
    
    @property
    def stats(self) -> CircuitBreakerStats:
        """Current statistics (returns a copy)."""
        with self._lock:
            return CircuitBreakerStats(
                state=self._stats.state,
                failure_count=self._stats.failure_count,
                success_count=self._stats.success_count,
                last_failure_time=self._stats.last_failure_time,
                last_success_time=self._stats.last_success_time,
                total_requests=self._stats.total_requests,
                rejected_requests=self._stats.rejected_requests,
            )
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerException: When circuit is open
            Exception: Original function exceptions
        """
        with self._lock:
            self._stats.total_requests += 1
            
            # Check if circuit is open
            if self._stats.state == CircuitState.OPEN:
                if not self._should_attempt_reset():
                    self._stats.rejected_requests += 1
                    if self.config.graceful_degradation and self._fallback:
                        return self._fallback(*args, **kwargs)
                    raise CircuitBreakerException(self.name, self._stats.state)
                else:
                    self._stats.state = CircuitState.HALF_OPEN
                    self._stats.success_count = 0
        
        # Execute function
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    async def acall(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function with circuit breaker protection.
        
        Args:
            func: Async function to execute
            *args, **kwargs: Arguments for the function
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerException: When circuit is open
            Exception: Original function exceptions
        """
        with self._lock:
            self._stats.total_requests += 1
            
            # Check if circuit is open
            if self._stats.state == CircuitState.OPEN:
                if not self._should_attempt_reset():
                    self._stats.rejected_requests += 1
                    if self.config.graceful_degradation and self._fallback:
                        if asyncio.iscoroutinefunction(self._fallback):
                            return await self._fallback(*args, **kwargs)
                        else:
                            return self._fallback(*args, **kwargs)
                    raise CircuitBreakerException(self.name, self._stats.state)
                else:
                    self._stats.state = CircuitState.HALF_OPEN
                    self._stats.success_count = 0
        
        # Start health check if enabled and not already running
        if self.config.enable_health_check and not self._health_check_task:
            self._start_health_check()
        
        # Execute function
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def reset(self) -> None:
        """Reset circuit breaker to closed state."""
        with self._lock:
            self._stats.state = CircuitState.CLOSED
            self._stats.failure_count = 0
            self._stats.success_count = 0
            self._failure_times.clear()
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit should attempt to transition to half-open."""
        if self._stats.last_failure_time is None:
            return True
        return time.time() - self._stats.last_failure_time >= self.config.recovery_timeout
    
    def _on_success(self) -> None:
        """Handle successful function execution."""
        with self._lock:
            current_time = time.time()
            self._stats.last_success_time = current_time
            
            if self._stats.state == CircuitState.HALF_OPEN:
                self._stats.success_count += 1
                if self._stats.success_count >= self.config.success_threshold:
                    self._stats.state = CircuitState.CLOSED
                    self._stats.failure_count = 0
                    self._failure_times.clear()
            elif self._stats.state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                self._stats.failure_count = max(0, self._stats.failure_count - 1)
    
    def _on_failure(self) -> None:
        """Handle failed function execution."""
        with self._lock:
            current_time = time.time()
            self._stats.last_failure_time = current_time
            self._stats.failure_count += 1
            self._failure_times.append(current_time)
            
            # Clean old failure times outside monitoring window
            cutoff = current_time - self.config.monitor_window
            self._failure_times = [t for t in self._failure_times if t > cutoff]
            
            # Check if should open circuit
            if (self._stats.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN) and 
                len(self._failure_times) >= self.config.failure_threshold):
                self._stats.state = CircuitState.OPEN
    
    def _start_health_check(self) -> None:
        """Start periodic health check task."""
        if not self._health_check:
            return
            
        async def health_check_loop():
            while self._stats.state == CircuitState.OPEN:
                try:
                    await asyncio.sleep(self.config.health_check_interval)
                    
                    # Perform health check
                    is_healthy = False
                    if hasattr(self._health_check, 'ahealth_check'):
                        is_healthy = await self._health_check.ahealth_check()
                    elif asyncio.iscoroutinefunction(self._health_check):
                        is_healthy = await self._health_check()
                    else:
                        is_healthy = self._health_check()
                    
                    # If healthy, transition to half-open for recovery probe
                    if is_healthy:
                        with self._lock:
                            if self._stats.state == CircuitState.OPEN:
                                self._stats.state = CircuitState.HALF_OPEN
                                self._stats.success_count = 0
                        
                except asyncio.CancelledError:
                    break
                except Exception:
                    # Ignore health check errors
                    pass
        
        try:
            loop = asyncio.get_event_loop()
            self._health_check_task = loop.create_task(health_check_loop())
        except RuntimeError:
            # No event loop running, skip health check
            pass


class CircuitBreakerRegistry:
    """Registry for managing multiple circuit breakers by service name."""
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()
    
    def get_or_create(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        health_check: Optional[Union[Callable[[], bool], HealthCheckProtocol]] = None,
        fallback: Optional[Callable] = None,
    ) -> CircuitBreaker:
        """Get existing circuit breaker or create a new one.
        
        Args:
            name: Service name
            config: Configuration for new breakers
            health_check: Health check function for new breakers
            fallback: Fallback function for new breakers
            
        Returns:
            CircuitBreaker instance
        """
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(name, config, health_check, fallback)
            return self._breakers[name]
    
    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name.
        
        Args:
            name: Service name
            
        Returns:
            CircuitBreaker instance or None
        """
        with self._lock:
            return self._breakers.get(name)
    
    def remove(self, name: str) -> bool:
        """Remove circuit breaker by name.
        
        Args:
            name: Service name
            
        Returns:
            True if removed, False if not found
        """
        with self._lock:
            return self._breakers.pop(name, None) is not None
    
    def list_services(self) -> List[str]:
        """List all registered service names."""
        with self._lock:
            return list(self._breakers.keys())
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers."""
        with self._lock:
            return {name: breaker.stats.to_dict() for name, breaker in self._breakers.items()}
    
    def reset_all(self) -> None:
        """Reset all circuit breakers and clear the registry."""
        with self._lock:
            self._breakers.clear()


# Global registry instance for convenience (lazy initialization)
_global_registry = None
_global_registry_lock = threading.Lock()


def _get_global_registry() -> CircuitBreakerRegistry:
    """Get or create the global circuit breaker registry."""
    global _global_registry
    with _global_registry_lock:
        if _global_registry is None:
            _global_registry = CircuitBreakerRegistry()
        return _global_registry


def get_circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
    health_check: Optional[Union[Callable[[], bool], HealthCheckProtocol]] = None,
    fallback: Optional[Callable] = None,
) -> CircuitBreaker:
    """Get or create a circuit breaker from the global registry.
    
    Args:
        name: Service name
        config: Configuration for new breakers
        health_check: Health check function for new breakers
        fallback: Fallback function for new breakers
        
    Returns:
        CircuitBreaker instance
    """
    return _get_global_registry().get_or_create(name, config, health_check, fallback)


def get_all_circuit_breaker_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all circuit breakers in the global registry."""
    return _get_global_registry().get_all_stats()


def reset_all_circuit_breakers() -> None:
    """Reset all circuit breakers in the global registry."""
    _get_global_registry().reset_all()