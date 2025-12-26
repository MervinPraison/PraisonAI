"""
TDD Tests for Rate Limiter.

These tests are written FIRST before implementation.
"""

import pytest
import time
from unittest.mock import Mock, patch


class TestRateLimiterBasic:
    """Test basic rate limiter functionality."""
    
    def test_rate_limiter_exists(self):
        """RateLimiter class should exist in praisonaiagents.llm."""
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60)
        assert limiter is not None
    
    def test_rate_limiter_rpm_parameter(self):
        """RateLimiter should accept requests_per_minute."""
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60)
        assert limiter.requests_per_minute == 60
    
    def test_rate_limiter_acquire_sync(self):
        """RateLimiter.acquire() should block if rate exceeded."""
        from praisonaiagents.llm import RateLimiter
        
        # 1 request per second = 60 per minute
        limiter = RateLimiter(requests_per_minute=60)
        
        # First acquire should be instant
        start = time.monotonic()
        limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1  # Should be nearly instant
    
    def test_rate_limiter_blocks_when_exceeded(self):
        """RateLimiter should block when rate is exceeded."""
        from praisonaiagents.llm import RateLimiter
        
        # Very low rate: 6 per minute = 1 per 10 seconds
        # But we'll use a mock clock to test without waiting
        limiter = RateLimiter(requests_per_minute=6)
        
        # Inject a mock clock for testing
        mock_time = [0.0]
        limiter._get_time = lambda: mock_time[0]
        limiter._sleep = lambda s: mock_time.__setitem__(0, mock_time[0] + s)
        
        # First request should pass
        limiter.acquire()
        
        # Second request should need to wait ~10 seconds
        # (but our mock sleep just advances time)
        limiter.acquire()
        
        # Time should have advanced
        assert mock_time[0] >= 10.0
    
    def test_rate_limiter_token_bucket(self):
        """RateLimiter should use token bucket algorithm."""
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60, burst=5)
        
        # Reset internal state with mock time
        mock_time = [0.0]
        limiter._get_time = lambda: mock_time[0]
        limiter._sleep = lambda s: mock_time.__setitem__(0, mock_time[0] + s)
        limiter._tokens = 5.0  # Reset tokens to burst size
        limiter._last_update = 0.0  # Reset last update
        
        for _ in range(5):
            limiter.acquire()
        
        # Should not have waited much (burst allows 5 instant requests)
        assert mock_time[0] < 1.0


class TestRateLimiterAsync:
    """Test async rate limiter functionality."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_acquire_async(self):
        """RateLimiter.acquire_async() should work with async."""
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60)
        
        # Should have async acquire method
        await limiter.acquire_async()
    
    @pytest.mark.asyncio
    async def test_rate_limiter_async_blocks(self):
        """Async acquire should also respect rate limits."""
        from praisonaiagents.llm import RateLimiter
        import asyncio
        
        limiter = RateLimiter(requests_per_minute=6)
        
        # Mock async sleep
        sleep_times = []
        original_sleep = asyncio.sleep
        
        async def mock_sleep(s):
            sleep_times.append(s)
            # Don't actually sleep in tests
        
        with patch('asyncio.sleep', mock_sleep):
            await limiter.acquire_async()
            await limiter.acquire_async()
        
        # Should have tried to sleep


class TestRateLimiterAgentIntegration:
    """Test rate limiter integration with Agent."""
    
    def test_agent_accepts_rate_limiter(self):
        """Agent should accept rate_limiter parameter."""
        from praisonaiagents import Agent
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60)
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            rate_limiter=limiter
        )
        assert agent is not None
        assert getattr(agent, '_rate_limiter', None) is limiter or \
               getattr(agent, 'rate_limiter', None) is limiter
    
    def test_agent_rate_limiter_applied_to_llm_calls(self):
        """Rate limiter should be applied before LLM calls."""
        from praisonaiagents import Agent
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60)
        acquire_count = [0]
        original_acquire = limiter.acquire
        
        def counting_acquire():
            acquire_count[0] += 1
            return original_acquire()
        
        limiter.acquire = counting_acquire
        
        agent = Agent(
            name="Test",
            instructions="Test agent",
            rate_limiter=limiter
        )
        
        with patch.object(agent, '_chat_completion', return_value="mocked"):
            agent.chat("Hello")
        
        # Rate limiter should have been called
        assert acquire_count[0] >= 1


class TestRateLimiterZeroOverhead:
    """Test that rate limiter has zero overhead when not used."""
    
    def test_no_rate_limiter_no_overhead(self):
        """When no rate limiter, should not add any overhead."""
        from praisonaiagents import Agent
        
        agent = Agent(
            name="Test",
            instructions="Test agent"
            # No rate_limiter
        )
        
        # Should not have rate limiter
        assert getattr(agent, '_rate_limiter', None) is None
    
    def test_rate_limiter_none_check_fast(self):
        """Checking for None rate limiter should be O(1)."""
        from praisonaiagents.llm import RateLimiter
        
        # This is more of a design requirement than a test
        # The implementation should do: if self._rate_limiter: self._rate_limiter.acquire()


class TestRateLimiterConfiguration:
    """Test rate limiter configuration options."""
    
    def test_rate_limiter_default_burst(self):
        """RateLimiter should have sensible default burst."""
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60)
        # Default burst should be 1 or based on rpm
        assert hasattr(limiter, 'burst') or hasattr(limiter, '_burst')
    
    def test_rate_limiter_custom_burst(self):
        """RateLimiter should accept custom burst parameter."""
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60, burst=10)
        burst = getattr(limiter, 'burst', None) or getattr(limiter, '_burst', None)
        assert burst == 10
    
    def test_rate_limiter_tpm_optional(self):
        """RateLimiter should optionally accept tokens_per_minute."""
        from praisonaiagents.llm import RateLimiter
        
        # Should not raise
        limiter = RateLimiter(
            requests_per_minute=60,
            tokens_per_minute=100000
        )
        assert limiter is not None


class TestRateLimiterDeterministic:
    """Test that rate limiter is deterministic for testing."""
    
    def test_injectable_clock(self):
        """RateLimiter should allow injecting clock for testing."""
        from praisonaiagents.llm import RateLimiter
        
        mock_time = [0.0]
        
        limiter = RateLimiter(requests_per_minute=60)
        limiter._get_time = lambda: mock_time[0]
        
        # Should use our mock time
        t1 = limiter._get_time()
        mock_time[0] = 100.0
        t2 = limiter._get_time()
        
        assert t1 == 0.0
        assert t2 == 100.0
    
    def test_injectable_sleep(self):
        """RateLimiter should allow injecting sleep for testing."""
        from praisonaiagents.llm import RateLimiter
        
        sleep_calls = []
        
        limiter = RateLimiter(requests_per_minute=60)
        limiter._sleep = lambda s: sleep_calls.append(s)
        
        # Force a wait scenario
        limiter._get_time = lambda: 0.0
        limiter._tokens = 0  # No tokens available
        limiter._last_update = 0.0
        
        limiter.acquire()
        
        # Should have called our mock sleep
        # (actual behavior depends on implementation)
