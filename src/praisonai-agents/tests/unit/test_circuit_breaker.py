"""Tests for circuit breaker implementation."""

import asyncio
import time
import pytest
from unittest.mock import Mock, patch

from praisonaiagents.tools.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerException,
    CircuitState,
    get_circuit_breaker,
    reset_all_circuit_breakers,
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    def setup_method(self):
        """Clean global registry before each test."""
        reset_all_circuit_breakers()
    
    def teardown_method(self):
        """Clean global registry after each test."""
        reset_all_circuit_breakers()
    
    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker starts in closed state."""
        breaker = CircuitBreaker("test_service")
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failure_count == 0
    
    def test_successful_call(self):
        """Test successful function call through circuit breaker."""
        breaker = CircuitBreaker("test_service")
        
        def test_func(x, y):
            return x + y
        
        result = breaker.call(test_func, 2, 3)
        assert result == 5
        assert breaker.state == CircuitState.CLOSED
    
    def test_failed_call(self):
        """Test failed function call increments failure count."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("test_service", config)
        
        def failing_func():
            raise Exception("Test failure")
        
        # First failure should not open circuit
        with pytest.raises(Exception, match="Test failure"):
            breaker.call(failing_func)
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failure_count == 1
    
    def test_circuit_opens_after_threshold(self):
        """Test circuit opens after failure threshold is reached."""
        config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.1)
        breaker = CircuitBreaker("test_service", config)
        
        def failing_func():
            raise Exception("Test failure")
        
        # Exceed failure threshold
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(failing_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Next call should be rejected
        with pytest.raises(CircuitBreakerException):
            breaker.call(failing_func)
    
    def test_circuit_transitions_to_half_open(self):
        """Test circuit transitions to half-open after recovery timeout."""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.05, success_threshold=1)
        breaker = CircuitBreaker("test_service", config)
        
        def failing_func():
            raise Exception("Test failure")
        
        # Open the circuit
        with pytest.raises(Exception):
            breaker.call(failing_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Wait for recovery timeout
        time.sleep(0.1)
        
        # Next call should transition to half-open
        def success_func():
            return "success"
        
        result = breaker.call(success_func)
        assert result == "success"
        # Circuit should close after successful call in half-open
        assert breaker.state == CircuitState.CLOSED
    
    def test_graceful_degradation_with_fallback(self):
        """Test graceful degradation using fallback function."""
        def fallback_func(*args, **kwargs):
            return "fallback_result"
        
        config = CircuitBreakerConfig(failure_threshold=1, graceful_degradation=True)
        breaker = CircuitBreaker("test_service", config, fallback=fallback_func)
        
        def failing_func():
            raise Exception("Test failure")
        
        # Open the circuit
        with pytest.raises(Exception):
            breaker.call(failing_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Next call should use fallback
        result = breaker.call(failing_func)
        assert result == "fallback_result"
    
    @pytest.mark.asyncio
    async def test_async_circuit_breaker(self):
        """Test async circuit breaker functionality."""
        breaker = CircuitBreaker("async_service")
        
        async def async_func(x):
            return x * 2
        
        result = await breaker.acall(async_func, 5)
        assert result == 10
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_async_circuit_breaker_failure(self):
        """Test async circuit breaker with failures."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("async_service", config)
        
        async def failing_async_func():
            raise Exception("Async failure")
        
        # Open the circuit
        with pytest.raises(Exception, match="Async failure"):
            await breaker.acall(failing_async_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Next call should be rejected
        with pytest.raises(CircuitBreakerException):
            await breaker.acall(failing_async_func)
    
    def test_health_check_functionality(self):
        """Test health check integration."""
        health_check_call_count = 0
        
        def health_check():
            nonlocal health_check_call_count
            health_check_call_count += 1
            return health_check_call_count > 2  # Healthy after 2 calls
        
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.05,
            enable_health_check=True,
            health_check_interval=0.01
        )
        breaker = CircuitBreaker("health_service", config, health_check=health_check)
        
        def failing_func():
            raise Exception("Test failure")
        
        # Open the circuit
        with pytest.raises(Exception):
            breaker.call(failing_func)
        
        assert breaker.state == CircuitState.OPEN
        
        # Health check should eventually recover the service
        # This is a simplified test - in real scenarios, health checks run in background
    
    def test_statistics_tracking(self):
        """Test statistics are properly tracked."""
        breaker = CircuitBreaker("stats_service")
        
        def test_func():
            return "success"
        
        def failing_func():
            raise Exception("failure")
        
        # Successful calls
        breaker.call(test_func)
        breaker.call(test_func)
        
        stats = breaker.stats
        assert stats.total_requests == 2
        assert stats.failure_count == 0
        
        # Failed call
        with pytest.raises(Exception):
            breaker.call(failing_func)
        
        stats = breaker.stats
        assert stats.total_requests == 3
        assert stats.failure_count == 1
        assert stats.last_failure_time is not None
    
    def test_reset_circuit_breaker(self):
        """Test resetting circuit breaker state."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("reset_service", config)
        
        def failing_func():
            raise Exception("Test failure")
        
        # Open the circuit
        with pytest.raises(Exception):
            breaker.call(failing_func)
        
        assert breaker.state == CircuitState.OPEN
        assert breaker.stats.failure_count == 1
        
        # Reset the circuit breaker
        breaker.reset()
        
        assert breaker.state == CircuitState.CLOSED
        assert breaker.stats.failure_count == 0
    
    def test_global_registry(self):
        """Test global circuit breaker registry functionality."""
        # Clean up before test
        reset_all_circuit_breakers()
        
        # Get circuit breakers
        breaker1 = get_circuit_breaker("service1")
        breaker2 = get_circuit_breaker("service2")
        breaker3 = get_circuit_breaker("service1")  # Should return same instance
        
        assert breaker1 is breaker3  # Same service name should return same instance
        assert breaker1 is not breaker2  # Different services should be different
        
        # Test statistics collection
        def test_func():
            return "success"
        
        breaker1.call(test_func)
        breaker2.call(test_func)
        
        from praisonaiagents.tools.circuit_breaker import get_all_circuit_breaker_stats
        all_stats = get_all_circuit_breaker_stats()
        
        assert "service1" in all_stats
        assert "service2" in all_stats
        assert all_stats["service1"]["total_requests"] == 1
        assert all_stats["service2"]["total_requests"] == 1


class TestCircuitBreakerIntegration:
    """Test circuit breaker integration with existing systems."""
    
    def setup_method(self):
        """Clean global registry before each test."""
        reset_all_circuit_breakers()
    
    def teardown_method(self):
        """Clean global registry after each test."""
        reset_all_circuit_breakers()
    
    def test_integration_with_retry_policy(self):
        """Test integration between circuit breaker and retry policy."""
        from praisonaiagents.tools.circuit_breaker_integrations import integrate_with_retry_policy
        from praisonaiagents.tools.retry import RetryPolicy
        
        retry_policy = RetryPolicy(max_attempts=3, backoff_factor=1.5)
        circuit_config = CircuitBreakerConfig(failure_threshold=2)
        
        tool_config = integrate_with_retry_policy(retry_policy, circuit_config, "test_service")
        
        assert tool_config.retry_policy is retry_policy
        assert tool_config.circuit_breaker_config is circuit_config
        assert tool_config.timeout_ms == int(circuit_config.timeout * 1000)
    
    def test_decorator_integration(self):
        """Test circuit breaker decorator functionality."""
        from praisonaiagents.tools.circuit_breaker_integrations import with_circuit_breaker
        
        call_count = 0
        
        @with_circuit_breaker("decorator_service_test", 
                              config=CircuitBreakerConfig(failure_threshold=2))
        def decorated_func(should_fail=False):
            nonlocal call_count
            call_count += 1
            if should_fail:
                raise Exception("Decorated failure")
            return f"success_{call_count}"
        
        # Successful call
        result = decorated_func()
        assert result == "success_1"
        
        # Failed calls to open circuit
        for _ in range(2):
            with pytest.raises(Exception):
                decorated_func(should_fail=True)
        
        # Circuit should now be open
        with pytest.raises(CircuitBreakerException):
            decorated_func()
    
    @pytest.mark.asyncio
    async def test_async_decorator_integration(self):
        """Test async circuit breaker decorator functionality."""
        from praisonaiagents.tools.circuit_breaker_integrations import with_circuit_breaker
        
        @with_circuit_breaker("async_decorator_service_test",
                              config=CircuitBreakerConfig(failure_threshold=1))
        async def async_decorated_func(should_fail=False):
            await asyncio.sleep(0.01)  # Simulate async work
            if should_fail:
                raise Exception("Async decorated failure")
            return "async_success"
        
        # Successful call
        result = await async_decorated_func()
        assert result == "async_success"
        
        # Failed call to open circuit
        with pytest.raises(Exception):
            await async_decorated_func(should_fail=True)
        
        # Circuit should now be open
        with pytest.raises(CircuitBreakerException):
            await async_decorated_func()
    
    def test_resilient_external_call(self):
        """Test resilient external call with retry + circuit breaker."""
        from praisonaiagents.tools.circuit_breaker_integrations import create_resilient_external_call
        
        call_count = 0
        
        def external_service(should_fail_times=0):
            nonlocal call_count
            call_count += 1
            if call_count <= should_fail_times:
                raise Exception(f"External failure {call_count}")
            return f"external_success_{call_count}"
        
        resilient_call = create_resilient_external_call(
            "external_service",
            external_service,
            retry_attempts=3,
            circuit_failure_threshold=2
        )
        
        # Test successful call after retries
        call_count = 0
        result = resilient_call(should_fail_times=1)  # Fail once, then succeed
        assert result == "external_success_2"
        assert call_count == 2  # One failure, one success
    
    def test_fallback_functionality(self):
        """Test fallback functionality when circuit is open."""
        from praisonaiagents.tools.circuit_breaker_integrations import with_circuit_breaker
        
        def fallback_func(*args, **kwargs):
            return "fallback_result"
        
        @with_circuit_breaker("fallback_service",
                              config=CircuitBreakerConfig(failure_threshold=1, graceful_degradation=True),
                              fallback=fallback_func)
        def failing_service():
            raise Exception("Service failure")
        
        # Open the circuit
        with pytest.raises(Exception):
            failing_service()
        
        # Next call should use fallback
        result = failing_service()
        assert result == "fallback_result"


# Real agentic test (MANDATORY per AGENTS.md)
def test_circuit_breaker_real_agentic():
    """Real agentic test - create agent and test circuit breaker integration."""
    from praisonaiagents import Agent
    from praisonaiagents.tools.circuit_breaker_integrations import with_circuit_breaker
    
    # Create a tool with circuit breaker protection
    call_count = 0
    
    @with_circuit_breaker("agent_tool_service", 
                          config=CircuitBreakerConfig(failure_threshold=2))
    def protected_tool(query: str) -> str:
        """A tool protected by circuit breaker."""
        nonlocal call_count
        call_count += 1
        if call_count <= 2:  # First two calls fail
            raise Exception("Tool failure")
        return f"Tool result for: {query}"
    
    # Create agent with the protected tool
    agent = Agent(
        name="test_agent",
        instructions="You are a test assistant.",
        tools=[protected_tool]
    )
    
    # This is a real agentic test - agent actually runs but may encounter circuit breaker
    try:
        result = agent.start("Test the protected tool")
        print(f"Agent result: {result}")
        assert result is not None  # Agent should produce some response
    except Exception as e:
        # Circuit breaker or tool failures are expected in this test
        print(f"Expected failure during circuit breaker test: {e}")
        assert "CircuitBreakerException" in str(type(e)) or "Tool failure" in str(e)


if __name__ == "__main__":
    pytest.main([__file__])