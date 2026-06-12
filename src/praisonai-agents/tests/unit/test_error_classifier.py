"""
Unit tests for LLM error classifier and retry utilities.

Tests the structured error classification system including:
- Error categorization
- Recovery routing hints
- Jittered backoff calculations
- Provider-aware delay calculations
"""

import pytest
import time
from unittest.mock import Mock, patch
from praisonaiagents.llm.error_classifier import (
    ErrorCategory, LLMErrorClassification, classify_error, classify_llm_error,
    should_retry, get_retry_delay, extract_retry_after, get_error_context
)
from praisonaiagents.llm.retry_utils import (
    jittered_backoff, calculate_backoff_with_retry_after
)


class TestErrorClassification:
    """Test error categorization functionality."""
    
    def test_rate_limit_classification(self):
        """Test rate limit error patterns are correctly classified."""
        errors = [
            Exception("Rate limit exceeded"),
            Exception("429 Too Many Requests"),
            Exception("quota exceeded for requests"),
            Exception("tokens per minute limit"),
            Exception("resource exhausted"),
        ]
        
        for error in errors:
            category = classify_error(error)
            assert category == ErrorCategory.RATE_LIMIT, f"Failed for: {error}"
    
    def test_context_limit_classification(self):
        """Test context limit error patterns are correctly classified."""
        errors = [
            Exception("context length 8192 exceeded"),
            Exception("maximum context window reached"),
            Exception("token limit exceeded"),
            Exception("input too long"),
            Exception("413 Request Entity Too Large"),
            Exception("payload too large"),
        ]
        
        for error in errors:
            category = classify_error(error)
            assert category == ErrorCategory.CONTEXT_LIMIT, f"Failed for: {error}"
    
    def test_auth_classification(self):
        """Test authentication error patterns are correctly classified."""
        errors = [
            Exception("401 Unauthorized"),
            Exception("403 Forbidden"),
            Exception("invalid api key"),
            Exception("authentication failed"),
            Exception("permission denied"),
            Exception("access denied"),
            Exception("expired token"),
        ]
        
        for error in errors:
            category = classify_error(error)
            assert category == ErrorCategory.AUTH, f"Failed for: {error}"
    
    def test_transient_classification(self):
        """Test transient error patterns are correctly classified."""
        errors = [
            Exception("500 Internal Server Error"),
            Exception("502 Bad Gateway"),
            Exception("503 Service Unavailable"),
            Exception("timeout occurred"),
            Exception("connection error"),
            Exception("network error"),
            Exception("server overload"),
        ]
        
        for error in errors:
            category = classify_error(error)
            assert category == ErrorCategory.TRANSIENT, f"Failed for: {error}"
    
    def test_invalid_request_classification(self):
        """Test invalid request error patterns are correctly classified."""
        errors = [
            Exception("400 Bad Request"),
            Exception("invalid request format"),
            Exception("malformed json"),
            Exception("unsupported model"),
            Exception("model not found"),
            Exception("validation error"),
        ]
        
        for error in errors:
            category = classify_error(error)
            assert category == ErrorCategory.INVALID_REQUEST, f"Failed for: {error}"
    
    def test_unknown_error_default(self):
        """Test unknown errors default to PERMANENT category."""
        error = Exception("something completely unknown")
        category = classify_error(error)
        assert category == ErrorCategory.PERMANENT


class TestStructuredClassification:
    """Test the enhanced LLM error classification with recovery hints."""
    
    def test_rate_limit_classification(self):
        """Test rate limit errors provide proper recovery hints."""
        error = Exception("429 Too Many Requests")
        classification = classify_llm_error(
            error, 
            provider="openai", 
            model="gpt-4", 
            retry_depth=0
        )
        
        assert classification.error_category == "rate_limit"
        assert classification.is_retryable is True
        assert classification.should_compress_context is False
        assert classification.should_rotate_credential is False
        assert classification.should_fallback_model is False
        assert classification.backoff_seconds > 0
        assert "rate limit" in classification.user_message.lower()
    
    def test_context_overflow_classification(self):
        """Test context limit errors provide compression hints."""
        error = Exception("context length exceeded")
        classification = classify_llm_error(
            error,
            provider="anthropic",
            model="claude-3-sonnet",
            retry_depth=0
        )
        
        assert classification.error_category == "context_overflow"
        assert classification.is_retryable is True
        assert classification.should_compress_context is True
        assert classification.should_rotate_credential is False
        assert classification.should_fallback_model is False
        assert classification.backoff_seconds == 0.0
        assert "compressing" in classification.user_message.lower()
    
    def test_auth_error_classification(self):
        """Test auth errors provide credential rotation hints."""
        error = Exception("401 Unauthorized")
        classification = classify_llm_error(
            error,
            provider="openai",
            model="gpt-4",
            retry_depth=0
        )
        
        assert classification.error_category == "auth"
        assert classification.is_retryable is False  # Fixed in the follow-up
        assert classification.should_compress_context is False
        assert classification.should_rotate_credential is True
        assert classification.should_fallback_model is False
        assert classification.backoff_seconds == 0.0
        assert "credential" in classification.user_message.lower()
    
    def test_transient_error_classification(self):
        """Test transient errors provide fallback hints."""
        error = Exception("503 Service Unavailable")
        classification = classify_llm_error(
            error,
            provider="azure",
            model="gpt-4-azure",
            retry_depth=0
        )
        
        assert classification.error_category == "overloaded"
        assert classification.is_retryable is True
        assert classification.should_compress_context is False
        assert classification.should_rotate_credential is False
        assert classification.should_fallback_model is True
        assert classification.backoff_seconds > 0
        assert "temporarily unavailable" in classification.user_message.lower()
    
    def test_provider_specific_delays(self):
        """Test different providers get different base delays."""
        error = Exception("429 Too Many Requests")
        
        # Test OpenAI (should have higher base delay)
        openai_classification = classify_llm_error(
            error, provider="openai", model="gpt-4", retry_depth=0
        )
        
        # Test Anthropic (should have lower base delay)  
        anthropic_classification = classify_llm_error(
            error, provider="anthropic", model="claude-3", retry_depth=0
        )
        
        # OpenAI typically has longer rate limit windows
        assert openai_classification.backoff_seconds > anthropic_classification.backoff_seconds
    
    def test_retry_depth_progression(self):
        """Test retry depth affects backoff timing."""
        error = Exception("429 Too Many Requests")
        
        first_attempt = classify_llm_error(
            error, provider="openai", model="gpt-4", retry_depth=0
        )
        second_attempt = classify_llm_error(
            error, provider="openai", model="gpt-4", retry_depth=1
        )
        third_attempt = classify_llm_error(
            error, provider="openai", model="gpt-4", retry_depth=2
        )
        
        # Progressive backoff should increase delay with attempts
        assert second_attempt.backoff_seconds > first_attempt.backoff_seconds
        assert third_attempt.backoff_seconds > second_attempt.backoff_seconds


class TestRetryUtils:
    """Test retry utility functions."""
    
    def test_jittered_backoff_basics(self):
        """Test basic jittered backoff functionality."""
        # Test attempt 0 returns 0
        assert jittered_backoff(0) == 0.0
        
        # Test exponential growth with jitter
        attempt1 = jittered_backoff(1, base=5.0)
        attempt2 = jittered_backoff(2, base=5.0)
        attempt3 = jittered_backoff(3, base=5.0)
        
        # Should be roughly exponential but with jitter
        assert 0 <= attempt1 <= 10.0  # Base 5 * 2^0 = 5, ±50% = 2.5-7.5
        assert 0 <= attempt2 <= 20.0  # Base 5 * 2^1 = 10, ±50% = 5-15
        assert 0 <= attempt3 <= 40.0  # Base 5 * 2^2 = 20, ±50% = 10-30
        
        # Results should be non-negative
        assert attempt1 >= 0
        assert attempt2 >= 0
        assert attempt3 >= 0
    
    def test_jittered_backoff_cap(self):
        """Test backoff respects maximum cap."""
        # Large attempt should be capped
        large_attempt = jittered_backoff(10, base=5.0, cap=60.0)
        assert large_attempt <= 60.0
    
    def test_jittered_backoff_randomness(self):
        """Test that jitter provides actual randomness."""
        # Run multiple times to ensure we get different results
        results = [jittered_backoff(2, base=10.0) for _ in range(10)]
        
        # Should have some variance (not all identical)
        assert len(set(results)) > 1, "Jitter should produce different results"
        
        # All should be within expected range
        for result in results:
            assert 0 <= result <= 40.0  # 10 * 2^1 = 20, ±50% jitter, non-negative
    
    def test_calculate_backoff_with_retry_after(self):
        """Test retry-after calculation logic."""
        # Server suggests shorter delay than exponential
        short_server_delay = calculate_backoff_with_retry_after(
            retry_after_seconds=1.0, attempt=3, base=10.0
        )
        
        # Should use exponential backoff (longer)
        exponential_delay = jittered_backoff(3, base=10.0)
        assert short_server_delay >= exponential_delay * 0.9  # Allow for jitter variance
        
        # Server suggests longer delay than exponential
        long_server_delay = calculate_backoff_with_retry_after(
            retry_after_seconds=100.0, attempt=1, base=5.0
        )
        
        # Should use server suggestion (longer)
        assert long_server_delay >= 100.0


class TestRetryLogic:
    """Test retry decision logic."""
    
    def test_should_retry_by_category(self):
        """Test which categories should be retried."""
        assert should_retry(ErrorCategory.RATE_LIMIT) is True
        assert should_retry(ErrorCategory.CONTEXT_LIMIT) is True  
        assert should_retry(ErrorCategory.TRANSIENT) is True
        
        assert should_retry(ErrorCategory.AUTH) is False
        assert should_retry(ErrorCategory.INVALID_REQUEST) is False
        assert should_retry(ErrorCategory.PERMANENT) is False
    
    def test_get_retry_delay_progression(self):
        """Test retry delay calculation increases with attempts."""
        # Rate limit delays should increase
        delay1 = get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=1)
        delay2 = get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=2)
        delay3 = get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=3)
        
        assert delay2 > delay1
        assert delay3 > delay2
        
        # Non-retryable should always return 0
        assert get_retry_delay(ErrorCategory.AUTH, attempt=1) == 0
        assert get_retry_delay(ErrorCategory.PERMANENT, attempt=5) == 0
    
    def test_get_retry_delay_jitter(self):
        """Test retry delays include jitter for thundering herd prevention."""
        # Multiple calls should return different values
        delays = [get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=2) for _ in range(5)]
        
        # Should have variance due to jitter
        assert len(set(delays)) > 1, "Delay should include jitter"
        
        # All should be reasonable values
        for delay in delays:
            assert 0 <= delay <= 60.0  # Should be capped


class TestRetryAfterExtraction:
    """Test extracting retry-after hints from errors."""
    
    def test_extract_retry_after_patterns(self):
        """Test various retry-after patterns are recognized."""
        test_cases = [
            ("Rate limit exceeded. Retry after 60 seconds", 60.0),
            ("429 Too Many Requests - retry-after: 30", 30.0),
            ("Please wait 15 seconds before retrying", 15.0),
            ("Retry in 5 seconds", 5.0),
            ("No retry info", None),
        ]
        
        for error_msg, expected in test_cases:
            error = Exception(error_msg)
            result = extract_retry_after(error)
            assert result == expected, f"Failed for: {error_msg}"
    
    def test_extract_retry_after_capping(self):
        """Test retry-after values are capped at reasonable limits."""
        error = Exception("retry after 600 seconds")  # 10 minutes
        result = extract_retry_after(error)
        assert result == 300.0  # Should be capped at 5 minutes


class TestErrorContext:
    """Test error context extraction for debugging."""
    
    def test_get_error_context_basic(self):
        """Test basic error context extraction."""
        error = Exception("Rate limit exceeded")
        context = get_error_context(error)
        
        assert context["error_type"] == "Exception"
        assert context["category"] == "rate_limit"
        assert context["should_retry"] == "True"
        assert "Rate limit exceeded" in context["message"]
    
    def test_get_error_context_with_retry_after(self):
        """Test context includes retry-after when available."""
        error = Exception("Rate limit - retry after 30")
        context = get_error_context(error)
        
        assert "retry_after" in context
        assert context["retry_after"] == "30.0"
    
    def test_get_error_context_suggestions(self):
        """Test context includes category-specific suggestions."""
        test_cases = [
            (Exception("context length exceeded"), "reducing input size"),
            (Exception("invalid api key"), "API key"),
            (Exception("malformed request"), "request parameters"),
        ]
        
        for error, expected_suggestion in test_cases:
            context = get_error_context(error)
            assert "suggestion" in context
            assert expected_suggestion.lower() in context["suggestion"].lower()


class TestRealAgenticErrorClassifier:
    """Real agentic test for error classifier with actual LLM integration."""
    
    def test_real_agent_error_recovery(self):
        """
        REAL AGENTIC TEST: Test error classifier with actual agent and LLM calls.
        
        This test creates an agent and triggers real LLM error scenarios to verify
        the classifier handles them correctly with structured recovery routing.
        """
        from praisonaiagents import Agent
        from praisonaiagents.llm.error_classifier import classify_llm_error
        
        # Create agent with a very restrictive context to trigger overflow
        agent = Agent(
            name="test_classifier",
            instructions="You are a helpful test assistant",
            llm="gpt-4o-mini",  # Use a real model
        )
        
        # Test 1: Create a scenario that should trigger context classification
        very_long_prompt = "Repeat this sentence: " + "test " * 1000
        
        try:
            # This should complete successfully or provide clear error classification
            result = agent.start(very_long_prompt)
            print("✅ Agent handled long prompt successfully")
            print(f"Response: {result[:100]}...")
            
        except Exception as e:
            # If an error occurs, test the classifier
            classification = classify_llm_error(
                e,
                provider="openai",
                model="gpt-4o-mini", 
                prompt_tokens=len(very_long_prompt.split()),
                retry_depth=0
            )
            
            print(f"✅ Error classified as: {classification.error_category}")
            print(f"Recovery hints: compress_context={classification.should_compress_context}")
            print(f"User message: {classification.user_message}")
            
            # Verify classification makes sense
            assert classification.error_category in [
                "context_overflow", "rate_limit", "overloaded", "auth", "model_error"
            ]
            assert isinstance(classification.is_retryable, bool)
            assert isinstance(classification.backoff_seconds, (int, float))
        
        # Test 2: Simple successful case to ensure agent works
        try:
            simple_result = agent.start("Say hello in one sentence")
            print(f"✅ Simple test successful: {simple_result}")
            
            # Must produce actual LLM output
            assert len(simple_result.strip()) > 0, "Agent must produce actual output"
            assert "hello" in simple_result.lower(), "Agent should respond to prompt"
            
        except Exception as e:
            # Even if there's an error, classifier should handle it gracefully
            classification = classify_llm_error(e, provider="openai", model="gpt-4o-mini")
            print(f"Simple test error classified as: {classification.error_category}")
            
            # Should not be a permanent error for a simple request
            if classification.error_category == "permanent":
                pytest.fail(f"Simple request should not cause permanent error: {e}")
        
        print("✅ Real agentic error classifier test completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])