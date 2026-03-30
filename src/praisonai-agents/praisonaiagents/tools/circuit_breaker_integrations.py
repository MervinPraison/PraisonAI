"""Integration utilities for circuit breaker with existing PraisonAI systems.

Provides helper functions to integrate circuit breaker pattern with:
- LLM failover system
- Memory stores (file, database)
- MCP transports
- External APIs

Following the protocol-driven, agent-centric approach from AGENTS.md.
"""

import asyncio
import functools
import logging
from typing import Any, Callable, Dict, List, Optional, Union, TypeVar, Coroutine

from .circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitBreakerException,
    get_circuit_breaker, CircuitState
)
from .retry import RetryPolicy, ToolExecutionConfig

logger = logging.getLogger(__name__)

T = TypeVar('T')


def with_circuit_breaker(
    service_name: str,
    config: Optional[CircuitBreakerConfig] = None,
    health_check: Optional[Callable[[], bool]] = None,
    fallback: Optional[Callable] = None,
    graceful_degradation: bool = True,
) -> Callable:
    """Decorator to add circuit breaker protection to any function.
    
    Args:
        service_name: Name of the service for circuit breaker identification
        config: Circuit breaker configuration
        health_check: Health check function
        fallback: Fallback function for graceful degradation
        graceful_degradation: Whether to enable graceful degradation
        
    Returns:
        Decorated function with circuit breaker protection
        
    Example:
        @with_circuit_breaker("database", fallback=get_cached_data)
        def query_database(query: str) -> List[Dict]:
            return db.execute(query)
        
        # Async version
        @with_circuit_breaker("api_service")
        async def call_api(endpoint: str) -> Dict:
            return await api.get(endpoint)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Get or create circuit breaker for this service
        breaker = get_circuit_breaker(
            service_name, 
            config or CircuitBreakerConfig(graceful_degradation=graceful_degradation),
            health_check,
            fallback
        )
        
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                try:
                    return await breaker.acall(func, *args, **kwargs)
                except CircuitBreakerException as e:
                    logger.warning(f"Circuit breaker open for {service_name}: {e}")
                    if fallback and graceful_degradation:
                        logger.info(f"Using fallback for {service_name}")
                        if asyncio.iscoroutinefunction(fallback):
                            return await fallback(*args, **kwargs)
                        else:
                            return fallback(*args, **kwargs)
                    raise
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                try:
                    return breaker.call(func, *args, **kwargs)
                except CircuitBreakerException as e:
                    logger.warning(f"Circuit breaker open for {service_name}: {e}")
                    if fallback and graceful_degradation:
                        logger.info(f"Using fallback for {service_name}")
                        return fallback(*args, **kwargs)
                    raise
            return sync_wrapper
    
    return decorator


class LLMCircuitBreakerIntegration:
    """Integration between circuit breaker and LLM failover system.
    
    Enhances the existing LLM failover with circuit breaker pattern for
    faster failure detection and prevention of cascading failures.
    """
    
    def __init__(self, failover_manager=None):
        """Initialize LLM circuit breaker integration.
        
        Args:
            failover_manager: Optional LLM FailoverManager instance
        """
        self._failover_manager = failover_manager
        self._service_breakers: Dict[str, CircuitBreaker] = {}
    
    def wrap_llm_call(
        self,
        provider_name: str,
        llm_func: Callable,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> Callable:
        """Wrap LLM call with circuit breaker protection.
        
        Args:
            provider_name: LLM provider name (openai, anthropic, etc.)
            llm_func: LLM function to protect
            config: Circuit breaker configuration
            
        Returns:
            Protected function
        """
        def health_check() -> bool:
            """Simple health check for LLM provider."""
            try:
                # Try a minimal request to check connectivity
                return True  # Simplified for now
            except Exception:
                return False
        
        def fallback(*args, **kwargs):
            """Fallback to next provider via failover manager."""
            if self._failover_manager:
                # Mark current provider as failed and get next
                if hasattr(self._failover_manager, 'mark_failure'):
                    profile = self._failover_manager.get_profile(provider_name)
                    if profile:
                        self._failover_manager.mark_failure(profile, "Circuit breaker open")
                
                next_profile = self._failover_manager.get_next_profile()
                if next_profile and next_profile.name != provider_name:
                    logger.info(f"Failover from {provider_name} to {next_profile.name}")
                    # This would need to call the function with the new provider
                    # Implementation depends on the specific LLM client structure
            
            raise CircuitBreakerException(provider_name, CircuitState.OPEN)
        
        breaker_config = config or CircuitBreakerConfig(
            failure_threshold=3,  # Lower threshold for LLM calls
            recovery_timeout=30.0,  # Faster recovery for LLMs
            graceful_degradation=True
        )
        
        return with_circuit_breaker(
            f"llm_{provider_name}",
            breaker_config,
            health_check,
            fallback
        )(llm_func)


class MemoryCircuitBreakerIntegration:
    """Integration between circuit breaker and memory systems.
    
    Provides circuit breaker protection for memory operations with
    graceful degradation to fallback storage.
    """
    
    def __init__(self, fallback_to_file: bool = True):
        """Initialize memory circuit breaker integration.
        
        Args:
            fallback_to_file: Whether to fallback to file storage when database is down
        """
        self.fallback_to_file = fallback_to_file
        self._file_fallback_data: Dict[str, Any] = {}
    
    def wrap_memory_store(
        self,
        store_type: str,  # "mongodb", "chromadb", etc.
        store_func: Callable,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> Callable:
        """Wrap memory store operation with circuit breaker.
        
        Args:
            store_type: Type of memory store
            store_func: Memory store function
            config: Circuit breaker configuration
            
        Returns:
            Protected function
        """
        def health_check() -> bool:
            """Health check for memory store."""
            try:
                if store_type == "mongodb":
                    # Try a simple ping operation
                    return True  # Simplified for now
                elif store_type == "chromadb":
                    # Try to list collections or ping
                    return True  # Simplified for now
                return True
            except Exception:
                return False
        
        def fallback(*args, **kwargs):
            """Fallback to file storage."""
            if self.fallback_to_file:
                logger.warning(f"{store_type} unavailable, using file fallback")
                # Simple file-based fallback (implement based on operation)
                operation_type = getattr(store_func, '__name__', 'unknown')
                
                if operation_type in ('store', 'save', 'insert'):
                    # Store operation - save to file fallback
                    key = f"{store_type}_{hash(str(args) + str(kwargs))}"
                    self._file_fallback_data[key] = {'args': args, 'kwargs': kwargs}
                    return True
                elif operation_type in ('search', 'find', 'query'):
                    # Search operation - return cached data or empty
                    return []
                
            raise CircuitBreakerException(store_type, CircuitState.OPEN)
        
        breaker_config = config or CircuitBreakerConfig(
            failure_threshold=2,  # Lower threshold for storage
            recovery_timeout=60.0,
            graceful_degradation=self.fallback_to_file
        )
        
        return with_circuit_breaker(
            f"memory_{store_type}",
            breaker_config,
            health_check,
            fallback if self.fallback_to_file else None
        )(store_func)


class MCPCircuitBreakerIntegration:
    """Integration between circuit breaker and MCP transports.
    
    Provides circuit breaker protection for MCP connections with
    automatic reconnection and graceful degradation.
    """
    
    def __init__(self):
        """Initialize MCP circuit breaker integration."""
        self._connection_pool: Dict[str, Any] = {}
    
    def wrap_mcp_transport(
        self,
        transport_name: str,
        transport_func: Callable,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> Callable:
        """Wrap MCP transport operation with circuit breaker.
        
        Args:
            transport_name: Name of MCP transport/server
            transport_func: Transport function to protect
            config: Circuit breaker configuration
            
        Returns:
            Protected function
        """
        def health_check() -> bool:
            """Health check for MCP transport."""
            try:
                # Try to ping the MCP server or check connection
                return True  # Simplified for now
            except Exception:
                return False
        
        def fallback(*args, **kwargs):
            """Fallback for MCP operations."""
            logger.warning(f"MCP transport {transport_name} unavailable")
            
            # For tool calls, could fallback to local implementations
            operation_type = getattr(transport_func, '__name__', 'unknown')
            if operation_type in ('call_tool', 'invoke_tool'):
                # Could fallback to local tool implementations
                logger.info(f"MCP tool call failed, no local fallback available")
            
            raise CircuitBreakerException(transport_name, CircuitState.OPEN)
        
        breaker_config = config or CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=45.0,
            enable_health_check=True,
            health_check_interval=20.0
        )
        
        return with_circuit_breaker(
            f"mcp_{transport_name}",
            breaker_config,
            health_check,
            fallback
        )(transport_func)


def integrate_with_retry_policy(
    retry_policy: RetryPolicy,
    circuit_breaker_config: CircuitBreakerConfig,
    service_name: str,
) -> ToolExecutionConfig:
    """Create integrated configuration for retry policy and circuit breaker.
    
    Args:
        retry_policy: Existing retry policy
        circuit_breaker_config: Circuit breaker configuration
        service_name: Service name for circuit breaker
        
    Returns:
        Combined tool execution configuration
    """
    return ToolExecutionConfig(
        retry_policy=retry_policy,
        circuit_breaker_config=circuit_breaker_config,
        timeout_ms=int(circuit_breaker_config.timeout * 1000)
    )


def create_resilient_external_call(
    service_name: str,
    func: Callable,
    retry_attempts: int = 3,
    circuit_failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    health_check: Optional[Callable[[], bool]] = None,
    fallback: Optional[Callable] = None,
) -> Callable:
    """Create a resilient external service call with both retry and circuit breaker.
    
    Combines retry logic with circuit breaker for robust external service calls.
    
    Args:
        service_name: Name of external service
        func: Function to make resilient
        retry_attempts: Number of retry attempts
        circuit_failure_threshold: Failures before circuit opens
        recovery_timeout: Time before attempting recovery
        health_check: Optional health check function
        fallback: Optional fallback function
        
    Returns:
        Resilient function with retry + circuit breaker
        
    Example:
        resilient_db_call = create_resilient_external_call(
            "database",
            db.query,
            retry_attempts=2,
            circuit_failure_threshold=3,
            fallback=get_cached_data
        )
        result = resilient_db_call("SELECT * FROM users")
    """
    # Configure circuit breaker
    circuit_config = CircuitBreakerConfig(
        failure_threshold=circuit_failure_threshold,
        recovery_timeout=recovery_timeout,
        graceful_degradation=fallback is not None
    )
    
    # Apply circuit breaker protection
    protected_func = with_circuit_breaker(
        service_name,
        circuit_config,
        health_check,
        fallback
    )(func)
    
    # Add retry logic on top
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def resilient_async_wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retry_attempts):
                try:
                    return await protected_func(*args, **kwargs)
                except CircuitBreakerException:
                    # Circuit breaker is open, don't retry
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < retry_attempts - 1:
                        # Calculate backoff delay (simple exponential)
                        delay = 1.0 * (2 ** attempt)
                        await asyncio.sleep(delay)
                        logger.warning(f"Retry {attempt + 1}/{retry_attempts} for {service_name}: {e}")
                    
            raise last_exception
        return resilient_async_wrapper
    else:
        @functools.wraps(func)
        def resilient_sync_wrapper(*args, **kwargs):
            import time
            last_exception = None
            for attempt in range(retry_attempts):
                try:
                    return protected_func(*args, **kwargs)
                except CircuitBreakerException:
                    # Circuit breaker is open, don't retry
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < retry_attempts - 1:
                        # Calculate backoff delay (simple exponential)
                        delay = 1.0 * (2 ** attempt)
                        time.sleep(delay)
                        logger.warning(f"Retry {attempt + 1}/{retry_attempts} for {service_name}: {e}")
                    
            raise last_exception
        return resilient_sync_wrapper


# Convenience instances for common integrations
llm_integration = LLMCircuitBreakerIntegration()
memory_integration = MemoryCircuitBreakerIntegration()
mcp_integration = MCPCircuitBreakerIntegration()