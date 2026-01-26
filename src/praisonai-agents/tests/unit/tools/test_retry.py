"""Unit tests for tools/retry.py"""
from praisonaiagents.tools.retry import (
    RetryPolicy,
    FallbackChain,
    ToolExecutionConfig,
)


class TestRetryPolicy:
    """Tests for RetryPolicy dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        policy = RetryPolicy()
        assert policy.max_attempts == 3
        assert policy.backoff_factor == 2.0
        assert policy.initial_delay_ms == 1000
        assert policy.max_delay_ms == 30000
        assert "timeout" in policy.retry_on
        assert "rate_limit" in policy.retry_on
        assert "connection_error" in policy.retry_on
        assert policy.jitter is False
        assert policy.jitter_factor == 0.25
    
    def test_custom_values(self):
        """Test custom configuration."""
        policy = RetryPolicy(
            max_attempts=5,
            backoff_factor=1.5,
            initial_delay_ms=500,
            max_delay_ms=10000,
            retry_on={"custom_error"},
            jitter=True,
            jitter_factor=0.1
        )
        assert policy.max_attempts == 5
        assert policy.backoff_factor == 1.5
        assert policy.initial_delay_ms == 500
        assert policy.max_delay_ms == 10000
        assert policy.retry_on == {"custom_error"}
        assert policy.jitter is True
        assert policy.jitter_factor == 0.1
    
    def test_should_retry_within_attempts(self):
        """Test should_retry returns True within max_attempts."""
        policy = RetryPolicy(max_attempts=3)
        assert policy.should_retry("timeout", 0) is True
        assert policy.should_retry("timeout", 1) is True
        assert policy.should_retry("timeout", 2) is True
    
    def test_should_retry_at_max_attempts(self):
        """Test should_retry returns False at max_attempts."""
        policy = RetryPolicy(max_attempts=3)
        assert policy.should_retry("timeout", 3) is False
        assert policy.should_retry("timeout", 4) is False
    
    def test_should_retry_unknown_error(self):
        """Test should_retry returns False for unknown errors."""
        policy = RetryPolicy()
        assert policy.should_retry("unknown_error", 0) is False
    
    def test_should_retry_custom_errors(self):
        """Test should_retry with custom error types."""
        policy = RetryPolicy(retry_on={"my_error", "other_error"})
        assert policy.should_retry("my_error", 0) is True
        assert policy.should_retry("other_error", 0) is True
        assert policy.should_retry("timeout", 0) is False
    
    def test_get_delay_ms_exponential(self):
        """Test exponential backoff calculation."""
        policy = RetryPolicy(
            initial_delay_ms=1000,
            backoff_factor=2.0,
            max_delay_ms=30000,
            jitter=False
        )
        assert policy.get_delay_ms(0) == 1000   # 1000 * 2^0
        assert policy.get_delay_ms(1) == 2000   # 1000 * 2^1
        assert policy.get_delay_ms(2) == 4000   # 1000 * 2^2
        assert policy.get_delay_ms(3) == 8000   # 1000 * 2^3
    
    def test_get_delay_ms_capped(self):
        """Test delay is capped at max_delay_ms."""
        policy = RetryPolicy(
            initial_delay_ms=1000,
            backoff_factor=2.0,
            max_delay_ms=5000,
            jitter=False
        )
        assert policy.get_delay_ms(10) == 5000  # Would be 1024000, capped
    
    def test_get_delay_ms_with_jitter(self):
        """Test jitter produces varying delays."""
        policy = RetryPolicy(jitter=True, jitter_factor=0.25)
        delays = [policy.get_delay_ms(0) for _ in range(20)]
        # With 25% jitter, delays should vary
        assert len(set(delays)) > 1
        # All delays should be within expected range (±25%)
        for delay in delays:
            assert 750 <= delay <= 1250
    
    def test_validation_max_attempts(self):
        """Test validation rejects invalid max_attempts."""
        try:
            RetryPolicy(max_attempts=0)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "max_attempts" in str(e)
    
    def test_validation_backoff_factor(self):
        """Test validation rejects backoff_factor < 1."""
        try:
            RetryPolicy(backoff_factor=0.5)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "backoff_factor" in str(e)
    
    def test_validation_initial_delay(self):
        """Test validation rejects negative initial_delay_ms."""
        try:
            RetryPolicy(initial_delay_ms=-1)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "initial_delay_ms" in str(e)
    
    def test_validation_max_less_than_initial(self):
        """Test validation rejects max_delay_ms < initial_delay_ms."""
        try:
            RetryPolicy(initial_delay_ms=1000, max_delay_ms=500)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "max_delay_ms" in str(e)
    
    def test_validation_jitter_factor(self):
        """Test validation rejects jitter_factor outside [0, 1]."""
        try:
            RetryPolicy(jitter_factor=1.5)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "jitter_factor" in str(e)
        
        try:
            RetryPolicy(jitter_factor=-0.1)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "jitter_factor" in str(e)


class TestFallbackChain:
    """Tests for FallbackChain dataclass."""
    
    def test_default_values(self):
        """Test default configuration."""
        chain = FallbackChain()
        assert chain.tools == []
        assert chain.stop_on_success is True
        assert len(chain) == 0
    
    def test_with_tools(self):
        """Test chain with tools."""
        chain = FallbackChain(tools=["primary", "secondary", "fallback"])
        assert len(chain) == 3
        assert chain.tools == ["primary", "secondary", "fallback"]
    
    def test_iteration(self):
        """Test chain is iterable."""
        chain = FallbackChain(tools=["a", "b", "c"])
        result = list(chain)
        assert result == ["a", "b", "c"]
    
    def test_stop_on_success_false(self):
        """Test stop_on_success can be disabled."""
        chain = FallbackChain(tools=["a", "b"], stop_on_success=False)
        assert chain.stop_on_success is False


class TestToolExecutionConfig:
    """Tests for ToolExecutionConfig dataclass."""
    
    def test_default_values(self):
        """Test default configuration."""
        config = ToolExecutionConfig()
        assert config.retry_policy is None
        assert config.fallback_chain is None
        assert config.timeout_ms is None
    
    def test_with_all_options(self):
        """Test configuration with all options."""
        config = ToolExecutionConfig(
            retry_policy=RetryPolicy(max_attempts=5),
            fallback_chain=FallbackChain(tools=["a", "b"]),
            timeout_ms=5000
        )
        assert config.retry_policy.max_attempts == 5
        assert len(config.fallback_chain) == 2
        assert config.timeout_ms == 5000
    
    def test_default_factory(self):
        """Test default() factory method."""
        config = ToolExecutionConfig.default()
        assert config.retry_policy is not None
        assert config.retry_policy.max_attempts == 3
        assert config.fallback_chain is None
        assert config.timeout_ms is None
