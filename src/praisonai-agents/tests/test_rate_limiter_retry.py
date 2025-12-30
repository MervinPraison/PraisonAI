"""
Comprehensive tests for rate limiting and retry functionality.
Tests for issue #1086 - tokens_per_minute rate limiting and 429 error auto-retry.
"""
import time
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestRetryDelayParsing:
    """Test retry delay parsing from various error message formats."""

    def test_parse_json_format(self):
        """Test parsing JSON format: "retryDelay": "58s" """
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        msg = '{"error": {"details": [{"@type": "RetryInfo", "retryDelay": "58s"}]}}'
        assert llm._parse_retry_delay(msg) == 58.0

    def test_parse_plain_format(self):
        """Test parsing plain format: retry after 30 seconds"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        msg = 'retry after 30 seconds'
        assert llm._parse_retry_delay(msg) == 30.0

    def test_parse_wait_format(self):
        """Test parsing wait format: wait 45 seconds"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        msg = 'Please wait 45 seconds before retrying'
        assert llm._parse_retry_delay(msg) == 45.0

    def test_parse_try_again_format(self):
        """Test parsing try again format: try again in 60"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        msg = 'Rate limited. Please try again in 60 seconds'
        assert llm._parse_retry_delay(msg) == 60.0

    def test_parse_retry_after_header(self):
        """Test parsing Retry-After header format"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        msg = 'Retry-After: 120'
        assert llm._parse_retry_delay(msg) == 120.0

    def test_parse_returns_default_on_no_match(self):
        """Test that default is returned when no pattern matches"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        msg = 'Some random error without delay info'
        assert llm._parse_retry_delay(msg) == 60.0  # Default retry_delay

    def test_parse_clamps_huge_delay(self):
        """Test that huge delays are clamped to max_retry_delay"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        msg = 'retry after 999999 seconds'
        delay = llm._parse_retry_delay(msg)
        assert delay <= 300  # Default max is 300 seconds


class TestRateLimitErrorDetection:
    """Test rate limit error detection."""

    def test_detect_429_error(self):
        """Test detection of 429 status code"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        e = Exception("429 Too Many Requests")
        assert llm._is_rate_limit_error(e) is True

    def test_detect_rate_limit_text(self):
        """Test detection of rate limit text"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        e = Exception("Rate limit exceeded")
        assert llm._is_rate_limit_error(e) is True

    def test_detect_resource_exhausted(self):
        """Test detection of RESOURCE_EXHAUSTED error"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        e = Exception("RESOURCE_EXHAUSTED: quota exceeded")
        assert llm._is_rate_limit_error(e) is True

    def test_detect_tokens_per_minute(self):
        """Test detection of tokens per minute quota error"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        e = Exception("tokens per minute quota exceeded")
        assert llm._is_rate_limit_error(e) is True

    def test_non_rate_limit_error(self):
        """Test that non-rate-limit errors are not detected"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        e = Exception("Connection timeout")
        assert llm._is_rate_limit_error(e) is False


class TestCallWithRetry:
    """Test the _call_with_retry method."""

    def test_success_on_first_try(self):
        """Test successful call on first attempt"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        mock_func = Mock(return_value="success")
        result = llm._call_with_retry(mock_func, "arg1", kwarg1="value1")
        
        assert result == "success"
        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    def test_retry_on_rate_limit(self):
        """Test retry behavior on rate limit error"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        llm._retry_delay = 0.01  # Short delay for testing
        
        # Fail twice, then succeed
        mock_func = Mock(side_effect=[
            Exception("429 Too Many Requests"),
            Exception("Rate limit exceeded"),
            "success"
        ])
        
        with patch('time.sleep'):
            result = llm._call_with_retry(mock_func)
        
        assert result == "success"
        assert mock_func.call_count == 3

    def test_no_retry_on_non_rate_limit_error(self):
        """Test that non-rate-limit errors are not retried"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        
        mock_func = Mock(side_effect=Exception("Connection error"))
        
        with pytest.raises(Exception, match="Connection error"):
            llm._call_with_retry(mock_func)
        
        mock_func.assert_called_once()

    def test_max_retries_exceeded(self):
        """Test that exception is raised after max retries"""
        from praisonaiagents.llm.llm import LLM
        llm = LLM(model="gpt-4o-mini")
        llm._max_retries = 2
        llm._retry_delay = 0.01
        
        mock_func = Mock(side_effect=Exception("429 Too Many Requests"))
        
        with patch('time.sleep'):
            with pytest.raises(Exception, match="429"):
                llm._call_with_retry(mock_func)
        
        # Should be called max_retries + 1 times (initial + retries)
        assert mock_func.call_count == 3


class TestTokenBucketAlgorithm:
    """Test token bucket rate limiting algorithm."""

    def test_acquire_tokens_without_blocking(self):
        """Test acquiring tokens when available"""
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(tokens_per_minute=60000, burst=1000)
        
        start = time.time()
        limiter.acquire_tokens(500)
        elapsed = time.time() - start
        
        assert elapsed < 0.5  # Should be nearly instant

    def test_token_refill_over_time(self):
        """Test that tokens refill over time"""
        from praisonaiagents.llm import RateLimiter
        
        # Create limiter with injectable time
        fake_time = [0.0]
        limiter = RateLimiter(tokens_per_minute=60000, burst=1000)
        limiter._get_time = lambda: fake_time[0]
        limiter._sleep = lambda x: None  # No-op sleep
        
        # Reset to known state
        limiter._api_tokens = 0.0
        limiter._api_tokens_last_update = 0.0
        
        # Advance time by 1 second (should add 1000 tokens at 60000/min = 1000/sec)
        fake_time[0] = 1.0
        limiter._refill_api_tokens()
        
        assert limiter._api_tokens == 1000.0

    def test_no_cap_on_internal_wait(self):
        """Test that internal wait time is NOT capped by max_retry_delay"""
        from praisonaiagents.llm import RateLimiter
        
        # Create limiter with low rate
        limiter = RateLimiter(tokens_per_minute=60, burst=1, max_retry_delay=10)
        
        # Calculate wait time for 100 tokens (should be ~100 seconds at 1 token/sec)
        limiter._api_tokens = 0.0
        wait = limiter._wait_time_for_tokens(100)
        
        # Wait should NOT be capped to max_retry_delay
        assert wait > 10  # Should be ~100 seconds


class TestRateLimiterWithLLM:
    """Test RateLimiter integration with LLM class."""

    def test_llm_with_rate_limiter(self):
        """Test that LLM accepts rate_limiter in extra_settings"""
        from praisonaiagents.llm.llm import LLM
        from praisonaiagents.llm import RateLimiter
        
        limiter = RateLimiter(requests_per_minute=60)
        llm = LLM(model="gpt-4o-mini", rate_limiter=limiter)
        
        assert llm._rate_limiter is limiter

    def test_llm_retry_settings(self):
        """Test that LLM accepts retry settings"""
        from praisonaiagents.llm.llm import LLM
        
        llm = LLM(model="gpt-4o-mini", max_retries=5, retry_delay=30)
        
        assert llm._max_retries == 5
        assert llm._retry_delay == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
