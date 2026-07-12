"""
Tests for error classification functionality.

Tests error categorization, retry logic, and delay calculation.
"""

import pytest
from praisonaiagents.llm.error_classifier import (
    ErrorCategory, classify_error, should_retry, get_retry_delay,
    extract_retry_after, get_error_context
)


class TestErrorClassification:
    
    def test_rate_limit_errors(self):
        """Test classification of rate limit errors."""
        test_cases = [
            Exception("Rate limit exceeded"),
            Exception("HTTP 429: Too many requests"),
            Exception("resource_exhausted: Quota exceeded"),
            Exception("tokens per minute limit reached"),
            Exception("RateLimitError: concurrent requests"),
        ]
        
        for error in test_cases:
            category = classify_error(error)
            assert category == ErrorCategory.RATE_LIMIT
            assert should_retry(category) is True
    
    def test_context_limit_errors(self):
        """Test classification of context length errors."""
        test_cases = [
            Exception("Context length 8192 exceeded"),
            Exception("maximum context window reached"),
            Exception("token limit exceeded"),
            Exception("input too long"),
            Exception("HTTP 413: Payload too large"),
            Exception("sequence too long for model"),
        ]
        
        for error in test_cases:
            category = classify_error(error)
            assert category == ErrorCategory.CONTEXT_LIMIT
            assert should_retry(category) is True
    
    def test_auth_errors(self):
        """Test classification of authentication errors.""" 
        test_cases = [
            Exception("Invalid API key"),
            Exception("HTTP 401: Unauthorized"),
            Exception("HTTP 403: Forbidden"),
            Exception("authentication failed"),
            Exception("permission denied"), 
            Exception("access denied"),
            Exception("invalid token"),
            Exception("expired token"),
        ]
        
        for error in test_cases:
            category = classify_error(error)
            assert category == ErrorCategory.AUTH
            assert should_retry(category) is False
    
    def test_invalid_request_errors(self):
        """Test classification of invalid request errors."""
        test_cases = [
            Exception("Invalid request format"),
            Exception("HTTP 400: Bad request"),
            Exception("malformed JSON"),
            Exception("invalid parameter: model"),
            Exception("unsupported model: fake-model"),
            Exception("validation error in request"),
        ]
        
        for error in test_cases:
            category = classify_error(error)
            assert category == ErrorCategory.INVALID_REQUEST
            assert should_retry(category) is False
    
    def test_transient_errors(self):
        """Test classification of transient errors."""
        test_cases = [
            Exception("Connection timeout"),
            Exception("HTTP 500: Internal server error"),
            Exception("HTTP 502: Bad gateway"),
            Exception("HTTP 503: Service unavailable"),
            Exception("HTTP 504: Gateway timeout"),
            Exception("network error"),
            Exception("temporary unavailable"),
            Exception("server overload"),
        ]
        
        for error in test_cases:
            category = classify_error(error)
            assert category == ErrorCategory.TRANSIENT
            assert should_retry(category) is True
    
    def test_unknown_errors(self):
        """Test that unknown errors are classified as permanent."""
        test_cases = [
            Exception("Some unknown error"),
            Exception("Custom application error"),
            ValueError("Invalid value"),
        ]
        
        for error in test_cases:
            category = classify_error(error)
            assert category == ErrorCategory.PERMANENT
            assert should_retry(category) is False


class TestTypeAndCodeClassification:
    """Classification by exception type / status code (not message substrings)."""

    def test_status_code_rate_limit_without_keyword(self):
        """A 429 with a message lacking the word 'rate' is still RATE_LIMIT."""
        class _ProviderError(Exception):
            status_code = 429

        error = _ProviderError("Quota temporarily unavailable, slow down")
        assert classify_error(error) == ErrorCategory.RATE_LIMIT

    def test_status_code_auth(self):
        class _ProviderError(Exception):
            status_code = 401
        assert classify_error(_ProviderError("no descriptive text")) == ErrorCategory.AUTH

    def test_status_code_from_response_object(self):
        class _Response:
            status_code = 503
        class _ProviderError(Exception):
            response = _Response()
        assert classify_error(_ProviderError("upstream hiccup")) == ErrorCategory.TRANSIENT

    def test_status_code_413_context_limit(self):
        class _ProviderError(Exception):
            status_code = 413
        assert classify_error(_ProviderError("payload rejected")) == ErrorCategory.CONTEXT_LIMIT

    def test_exception_class_name_rate_limit(self):
        """Provider SDK class name is matched even without a status code."""
        class RateLimitError(Exception):
            pass
        assert classify_error(RateLimitError("slow down please")) == ErrorCategory.RATE_LIMIT

    def test_exception_subclass_via_mro(self):
        class AuthenticationError(Exception):
            pass
        class ProviderAuthError(AuthenticationError):
            pass
        assert classify_error(ProviderAuthError("nope")) == ErrorCategory.AUTH

    def test_stdlib_timeout_error_is_transient(self):
        assert classify_error(TimeoutError("op timed out")) == ErrorCategory.TRANSIENT

    def test_stdlib_connection_error_is_transient(self):
        assert classify_error(ConnectionError("reset by peer")) == ErrorCategory.TRANSIENT

    def test_message_fallback_still_works(self):
        """Plain exceptions with no type/code still classify by message."""
        assert classify_error(Exception("Rate limit exceeded")) == ErrorCategory.RATE_LIMIT

    def test_string_code_is_ignored(self):
        """A non-numeric ``code`` attribute must not break classification."""
        class _ProviderError(Exception):
            code = "insufficient_quota"
        # No numeric status/type match -> falls through to message (unknown -> PERMANENT)
        assert classify_error(_ProviderError("something opaque")) == ErrorCategory.PERMANENT


class TestStructuredRetryAfter:
    """Retry-After extraction from structured headers/attributes."""

    def test_retry_after_from_response_headers(self):
        class _Response:
            headers = {"retry-after": "42"}
        class _ProviderError(Exception):
            response = _Response()
        assert extract_retry_after(_ProviderError("rate limited")) == 42.0

    def test_retry_after_from_error_headers(self):
        class _ProviderError(Exception):
            headers = {"Retry-After": "15"}
        assert extract_retry_after(_ProviderError("rate limited")) == 15.0

    def test_retry_after_attribute(self):
        class _ProviderError(Exception):
            retry_after = 7
        assert extract_retry_after(_ProviderError("rate limited")) == 7.0

    def test_structured_header_capped(self):
        class _Response:
            headers = {"retry-after": "9999"}
        class _ProviderError(Exception):
            response = _Response()
        assert extract_retry_after(_ProviderError("rate limited")) == 300.0

    def test_http_date_header_falls_back_to_message(self):
        """A non-numeric Retry-After (HTTP-date) falls back to message parsing."""
        class _Response:
            headers = {"retry-after": "Wed, 21 Oct 2025 07:28:00 GMT"}
        class _ProviderError(Exception):
            response = _Response()
        # No numeric header, no message pattern -> None
        assert extract_retry_after(_ProviderError("please slow down")) is None


class TestRetryLogic:
    
    def test_retry_delays(self):
        """Test retry delay ranges for different categories.

        After issue #1553, RATE_LIMIT and TRANSIENT use equal-jitter to prevent
        thundering-herd retry storms across multi-agent workflows. Delays are
        bounded in [base_delay, exp_max] rather than deterministic.
        """
        # Rate limit delays (exponential factor 3, jittered floor=base_delay=1.0)
        assert 1.0 <= get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=1) <= 3.0
        assert 1.0 <= get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=2) <= 9.0
        assert 1.0 <= get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=3) <= 27.0

        # Context limit delays remain deterministic (no contention concern)
        assert get_retry_delay(ErrorCategory.CONTEXT_LIMIT, attempt=1) == 0.5
        assert get_retry_delay(ErrorCategory.CONTEXT_LIMIT, attempt=2) == 0.5

        # Transient delays (exponential factor 2, jittered floor=base_delay=1.0)
        assert 1.0 <= get_retry_delay(ErrorCategory.TRANSIENT, attempt=1) <= 2.0
        assert 1.0 <= get_retry_delay(ErrorCategory.TRANSIENT, attempt=2) <= 4.0
        assert 1.0 <= get_retry_delay(ErrorCategory.TRANSIENT, attempt=3) <= 8.0

        # No retry for permanent errors
        assert get_retry_delay(ErrorCategory.AUTH, attempt=1) == 0
        assert get_retry_delay(ErrorCategory.INVALID_REQUEST, attempt=1) == 0
        assert get_retry_delay(ErrorCategory.PERMANENT, attempt=1) == 0

    def test_retry_delay_caps(self):
        """Test that jittered retry delays remain within their respective caps."""
        # Rate limit cap at 60 seconds (jittered floor=base_delay=1.0)
        assert 1.0 <= get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=10) <= 60.0

        # Transient cap at 30 seconds (jittered floor=base_delay=1.0)
        assert 1.0 <= get_retry_delay(ErrorCategory.TRANSIENT, attempt=10) <= 30.0

    def test_base_delay_scaling(self):
        """Test custom base delay scaling — base_delay sets the jitter floor."""
        assert 2.0 <= get_retry_delay(ErrorCategory.TRANSIENT, attempt=1, base_delay=2.0) <= 4.0
        assert 2.0 <= get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=1, base_delay=2.0) <= 6.0


class TestRetryAfterExtraction:
    
    def test_retry_after_patterns(self):
        """Test extraction of Retry-After values from errors."""
        test_cases = [
            (Exception("retry after 30 seconds"), 30.0),
            (Exception("Retry-After: 60"), 60.0), 
            (Exception("retry: 45"), 45.0),
            (Exception("wait 120 seconds"), 120.0),
            (Exception("Rate limited. 90 second cooldown"), 90.0),
        ]
        
        for error, expected in test_cases:
            delay = extract_retry_after(error)
            assert delay == expected
    
    def test_retry_after_cap(self):
        """Test that retry-after values are capped."""
        error = Exception("retry after 600 seconds")  # 10 minutes
        delay = extract_retry_after(error)
        assert delay == 300.0  # Capped at 5 minutes
    
    def test_no_retry_after(self):
        """Test handling when no retry-after is found."""
        error = Exception("Generic error message")
        delay = extract_retry_after(error)
        assert delay is None


class TestErrorContext:
    
    def test_basic_context(self):
        """Test basic error context extraction."""
        error = ValueError("Invalid input")
        context = get_error_context(error)
        
        assert context["error_type"] == "ValueError"
        assert context["category"] == ErrorCategory.PERMANENT.value
        assert context["should_retry"] == "False"
        assert "Invalid input" in context["message"]
    
    def test_rate_limit_context(self):
        """Test rate limit specific context."""
        error = Exception("Rate limit. Retry after 30 seconds")
        context = get_error_context(error)
        
        assert context["category"] == ErrorCategory.RATE_LIMIT.value
        assert context["should_retry"] == "True"
        assert "retry_after" in context
        assert context["retry_after"] == "30.0"
    
    def test_context_limit_context(self):
        """Test context limit specific context."""
        error = Exception("Context length exceeded")
        context = get_error_context(error)
        
        assert context["category"] == ErrorCategory.CONTEXT_LIMIT.value
        assert "suggestion" in context
        assert "compression" in context["suggestion"].lower()
    
    def test_auth_context(self):
        """Test auth error specific context."""
        error = Exception("Invalid API key")
        context = get_error_context(error)
        
        assert context["category"] == ErrorCategory.AUTH.value
        assert "suggestion" in context
        assert "api key" in context["suggestion"].lower()
    
    def test_long_message_truncation(self):
        """Test that long error messages are truncated."""
        long_message = "x" * 1000
        error = Exception(long_message)
        context = get_error_context(error)
        
        assert len(context["message"]) <= 500


class TestBackwardCompatibility:
    
    def test_rate_limit_backward_compat(self):
        """Test that existing rate limit patterns still work."""
        # These should match the patterns that were in _is_rate_limit_error
        test_cases = [
            Exception("429"),
            Exception("rate limit"),
            Exception("ratelimit"),
            Exception("too many request"),
            Exception("resource_exhausted"),
            Exception("quota exceeded"),
            Exception("tokens per minute"),
        ]
        
        for error in test_cases:
            category = classify_error(error)
            assert category == ErrorCategory.RATE_LIMIT
            
        # Test with existing _is_rate_limit_error logic (if available)
        try:
            from praisonaiagents.llm.llm import LLM
            llm = LLM(model="fake")
            
            for error in test_cases:
                # Both should agree on rate limit errors
                is_rate_limit = llm._is_rate_limit_error(error)
                is_classified_rate_limit = classify_error(error) == ErrorCategory.RATE_LIMIT
                assert is_rate_limit == is_classified_rate_limit
                
        except (ImportError, AttributeError):
            # Skip backward compatibility test if LLM not available
            pass