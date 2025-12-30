"""
Test for tokens_per_minute rate limiting functionality.
This test verifies the fix for issue #1086.
"""
import time


class TestTokensPerMinuteRateLimiter:
    """Test the enhanced RateLimiter with tokens_per_minute support."""

    def test_rate_limiter_import(self):
        """Test that RateLimiter can be imported."""
        from praisonaiagents.llm import RateLimiter
        assert RateLimiter is not None

    def test_rate_limiter_requests_per_minute(self):
        """Test basic requests_per_minute functionality."""
        from praisonaiagents.llm import RateLimiter

        limiter = RateLimiter(requests_per_minute=60, burst=2)
        assert limiter.requests_per_minute == 60
        assert limiter.burst == 2

        # Should acquire without waiting
        start = time.time()
        limiter.acquire()
        limiter.acquire()  # Second within burst
        elapsed = time.time() - start
        assert elapsed < 0.5  # Should be nearly instant

    def test_rate_limiter_tokens_per_minute(self):
        """Test tokens_per_minute functionality."""
        from praisonaiagents.llm import RateLimiter

        limiter = RateLimiter(tokens_per_minute=1000000)  # 1M tokens/min
        assert limiter.tokens_per_minute == 1000000

        # Should acquire tokens without waiting
        start = time.time()
        limiter.acquire_tokens(1000)
        elapsed = time.time() - start
        assert elapsed < 0.5

    def test_rate_limiter_repr(self):
        """Test string representation."""
        from praisonaiagents.llm import RateLimiter

        limiter1 = RateLimiter(requests_per_minute=60)
        assert 'rpm=60' in repr(limiter1)

        limiter2 = RateLimiter(tokens_per_minute=1000000)
        assert 'tpm=1000000' in repr(limiter2)

        limiter3 = RateLimiter(requests_per_minute=60, tokens_per_minute=1000000)
        assert 'rpm=60' in repr(limiter3)
        assert 'tpm=1000000' in repr(limiter3)

    def test_rate_limiter_available_tokens(self):
        """Test available tokens monitoring."""
        from praisonaiagents.llm import RateLimiter

        limiter = RateLimiter(tokens_per_minute=60000, burst=1000)
        initial = limiter.available_api_tokens
        assert initial > 0

        limiter.acquire_tokens(500)
        after = limiter.available_api_tokens
        assert after < initial

    def test_llm_rate_limit_parsing(self):
        """Test that LLM can parse retry delay from error messages."""
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o-mini")

        # Test JSON format
        msg1 = '{"error": {"details": [{"@type": "RetryInfo", "retryDelay": "58s"}]}}'
        delay1 = llm._parse_retry_delay(msg1)
        assert delay1 == 58.0

        # Test plain format
        msg2 = 'retry after 30 seconds'
        delay2 = llm._parse_retry_delay(msg2)
        assert delay2 == 30.0

    def test_llm_rate_limit_error_detection(self):
        """Test that LLM can detect rate limit errors."""
        from praisonaiagents.llm.llm import LLM

        llm = LLM(model="gpt-4o-mini")

        # Test 429 error detection
        class RateLimitError(Exception):
            pass

        e1 = RateLimitError("429 Too Many Requests")
        assert llm._is_rate_limit_error(e1)

        e2 = Exception("RESOURCE_EXHAUSTED: quota exceeded")
        assert llm._is_rate_limit_error(e2)

        e3 = Exception("tokens per minute quota exceeded")
        assert llm._is_rate_limit_error(e3)

        e4 = Exception("Some other error")
        assert not llm._is_rate_limit_error(e4)


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
