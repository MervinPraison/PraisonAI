"""
Unit tests for error classification system introduced in PR #1853.

Tests the AgentErrorKind taxonomy, FailoverDecision logic,
and classify_error_kind functionality.
"""

import pytest
from unittest.mock import Mock, patch
from praisonaiagents.errors import (
    AgentErrorKind, 
    FailoverDecision, 
    PraisonAIError, 
    LLMError,
    NetworkError,
    ToolExecutionError
)
from praisonaiagents.llm.llm import LLM


class TestAgentErrorKind:
    """Test the AgentErrorKind Literal type."""
    
    def test_valid_error_kinds(self):
        """Test that all error kinds are valid."""
        valid_kinds = [
            "auth", "auth_permanent", "rate_limit", "overloaded",
            "context_overflow", "idle_timeout", "billing",
            "model_not_found", "empty_response", "format_error", "unknown"
        ]
        
        for kind in valid_kinds:
            # These should not raise type errors
            error = PraisonAIError("test", error_category=kind)
            assert error.error_category == kind
    
    def test_legacy_error_category_mapping(self):
        """Test backward compatibility mapping for legacy error categories."""
        test_cases = [
            ("tool", "unknown"),
            ("llm", "unknown"),
            ("budget", "billing"),
            ("validation", "format_error"),
            ("network", "unknown"),
            ("handoff", "unknown"),
        ]
        
        for legacy, expected in test_cases:
            with pytest.warns(DeprecationWarning):
                error = PraisonAIError("test", error_category=legacy)
                assert error.error_category == expected
    
    def test_invalid_error_category_raises_error(self):
        """Test that invalid error categories raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported error_category"):
            PraisonAIError("test", error_category="invalid_category")


class TestFailoverDecision:
    """Test the FailoverDecision dataclass."""
    
    def test_failover_decision_creation(self):
        """Test creating FailoverDecision instances."""
        decision = FailoverDecision(
            action="retry",
            reason="rate_limit",
            backoff_ms=1000,
            is_retryable=True
        )
        
        assert decision.action == "retry"
        assert decision.reason == "rate_limit"
        assert decision.backoff_ms == 1000
        assert decision.is_retryable is True
    
    def test_failover_decision_defaults(self):
        """Test default values for FailoverDecision."""
        decision = FailoverDecision(
            action="surface_error",
            reason="auth_permanent"
        )
        
        assert decision.backoff_ms == 0
        assert decision.is_retryable is True


class TestClassifyErrorKind:
    """Test the LLM.classify_error_kind method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.llm = LLM(api_base="test", api_key="test")
    
    def test_auth_permanent_classification(self):
        """Test classification of permanent auth errors."""
        test_cases = [
            "Invalid API key provided",
            "API key not found",
            "Incorrect API key",
            "authentication_error"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "auth_permanent", f"Failed for: {error_msg}"
    
    def test_auth_retryable_classification(self):
        """Test classification of retryable auth errors."""
        test_cases = [
            "Unauthorized",
            "Authentication failed",
            "invalid_request_error",
            "openai_error"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "auth", f"Failed for: {error_msg}"
    
    def test_rate_limit_classification(self):
        """Test classification of rate limit errors."""
        test_cases = [
            "Rate limit exceeded",
            "Too many requests",
            "resource_exhausted",
            "usage limit reached"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "rate_limit", f"Failed for: {error_msg}"
    
    def test_rate_limit_with_status_code(self):
        """Test rate limit classification with status code."""
        error = Exception("Request failed")
        error.status_code = 429
        
        result = self.llm.classify_error_kind(error)
        assert result == "rate_limit"
    
    def test_context_overflow_classification(self):
        """Test classification of context overflow errors."""
        test_cases = [
            "maximum context length exceeded",
            "context window is too long",
            "context length exceeded",
            "input too long",
            "prompt too long"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "context_overflow", f"Failed for: {error_msg}"
    
    def test_model_not_found_classification(self):
        """Test classification of model not found errors."""
        test_cases = [
            "model not found",
            "unknown model",
            "invalid model",
            "model does not exist",
            "model not available"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "model_not_found", f"Failed for: {error_msg}"
    
    def test_billing_classification(self):
        """Test classification of billing errors."""
        test_cases = [
            "quota exceeded",
            "billing error",
            "payment required",
            "subscription expired",
            "insufficient credits"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "billing", f"Failed for: {error_msg}"
    
    def test_overloaded_classification(self):
        """Test classification of overloaded errors."""
        test_cases = [
            "server overloaded",
            "service unavailable",
            "try again later",
            "server busy"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "overloaded", f"Failed for: {error_msg}"
    
    def test_idle_timeout_classification(self):
        """Test classification of idle timeout errors."""
        test_cases = [
            "request timeout",
            "connection timeout",
            "timeout error",
            "idle timeout",
            "read timeout"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "idle_timeout", f"Failed for: {error_msg}"
    
    def test_empty_response_classification(self):
        """Test classification of empty response errors."""
        test_cases = [
            "empty response",
            "no content",
            "blank output",
            "null response"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "empty_response", f"Failed for: {error_msg}"
    
    def test_format_error_classification(self):
        """Test classification of format errors."""
        test_cases = [
            "json parse error",
            "malformed response",
            "invalid format",
            "parsing error",
            "decode error"
        ]
        
        for error_msg in test_cases:
            error = Exception(error_msg)
            result = self.llm.classify_error_kind(error)
            assert result == "format_error", f"Failed for: {error_msg}"
    
    def test_unknown_classification(self):
        """Test classification of unknown errors."""
        error = Exception("some random error message")
        result = self.llm.classify_error_kind(error)
        assert result == "unknown"


class TestResolveFailoverDecision:
    """Test the LLM.resolve_failover_decision method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.llm = LLM(api_base="test", api_key="test")
    
    def test_non_retryable_errors_surface_immediately(self):
        """Test that non-retryable errors surface immediately."""
        non_retryable_kinds = ["auth_permanent", "model_not_found", "format_error"]
        
        for kind in non_retryable_kinds:
            with patch.object(self.llm, 'classify_error_kind', return_value=kind):
                error = Exception("test error")
                attempt_state = {"attempt": 1, "max_retries": 3}
                
                decision = self.llm.resolve_failover_decision(error, attempt_state)
                
                assert decision.action == "surface_error"
                assert decision.reason == kind
                assert decision.is_retryable is False
    
    def test_billing_errors_surface_immediately(self):
        """Test that billing errors surface immediately (should be non-retryable)."""
        with patch.object(self.llm, 'classify_error_kind', return_value="billing"):
            error = Exception("quota exceeded")
            attempt_state = {"attempt": 1, "max_retries": 3}
            
            decision = self.llm.resolve_failover_decision(error, attempt_state)
            
            # This test documents current behavior - billing should surface immediately
            # but currently falls through to unknown retry logic
            # TODO: Fix this in the implementation
            assert decision.action == "surface_error"
            assert decision.reason == "billing"
            assert decision.is_retryable is False
    
    def test_rate_limit_retry_with_backoff(self):
        """Test that rate limit errors retry with backoff."""
        with patch.object(self.llm, 'classify_error_kind', return_value="rate_limit"):
            with patch.object(self.llm, '_parse_retry_delay', return_value=5):
                error = Exception("rate limit exceeded")
                attempt_state = {"attempt": 1, "max_retries": 3}
                
                decision = self.llm.resolve_failover_decision(error, attempt_state)
                
                assert decision.action == "retry"
                assert decision.reason == "rate_limit"
                assert decision.backoff_ms == 5000  # 5 seconds * 1000
                assert decision.is_retryable is True
    
    def test_auth_with_failover_manager_rotates_profile(self):
        """Test that auth errors with failover manager rotate profile."""
        mock_failover = Mock()
        self.llm._failover_manager = mock_failover
        
        with patch.object(self.llm, 'classify_error_kind', return_value="auth"):
            error = Exception("unauthorized")
            attempt_state = {"attempt": 1, "max_retries": 3}
            
            decision = self.llm.resolve_failover_decision(error, attempt_state)
            
            assert decision.action == "rotate_profile"
            assert decision.reason == "auth"
    
    def test_auth_without_failover_manager_surfaces(self):
        """Test that auth errors without failover manager surface."""
        self.llm._failover_manager = None
        
        with patch.object(self.llm, 'classify_error_kind', return_value="auth"):
            error = Exception("unauthorized")
            attempt_state = {"attempt": 1, "max_retries": 3}
            
            decision = self.llm.resolve_failover_decision(error, attempt_state)
            
            assert decision.action == "surface_error"
            assert decision.reason == "auth"
    
    def test_idle_timeout_with_circuit_breaker(self):
        """Test idle timeout handling with circuit breaker."""
        # Mock circuit breaker hit
        self.llm._idle_timeout_breaker.record_idle_timeout = Mock(return_value=True)
        
        with patch.object(self.llm, 'classify_error_kind', return_value="idle_timeout"):
            error = Exception("timeout")
            attempt_state = {"attempt": 1, "max_retries": 3}
            
            decision = self.llm.resolve_failover_decision(error, attempt_state)
            
            assert decision.action == "surface_error"
            assert decision.reason == "idle_timeout"
            # Verify circuit breaker was called
            self.llm._idle_timeout_breaker.record_idle_timeout.assert_called_once()
    
    def test_overloaded_retry_with_exponential_backoff(self):
        """Test that overloaded errors retry with exponential backoff."""
        with patch.object(self.llm, 'classify_error_kind', return_value="overloaded"):
            error = Exception("server overloaded")
            attempt_state = {"attempt": 2, "max_retries": 3}
            
            decision = self.llm.resolve_failover_decision(error, attempt_state)
            
            assert decision.action == "retry"
            assert decision.reason == "overloaded"
            # Should have exponential backoff: 2^(2-1) = 2 seconds * 1000 = 2000ms
            assert decision.backoff_ms == 2000
            assert decision.is_retryable is True
    
    def test_unknown_errors_retry_within_limit(self):
        """Test that unknown errors retry within attempt limit."""
        with patch.object(self.llm, 'classify_error_kind', return_value="unknown"):
            error = Exception("mysterious error")
            attempt_state = {"attempt": 1, "max_retries": 3}
            
            decision = self.llm.resolve_failover_decision(error, attempt_state)
            
            assert decision.action == "retry"
            assert decision.reason == "unknown"
            assert decision.is_retryable is True
    
    def test_unknown_errors_surface_after_max_retries(self):
        """Test that unknown errors surface after max retries."""
        with patch.object(self.llm, 'classify_error_kind', return_value="unknown"):
            error = Exception("mysterious error")
            attempt_state = {"attempt": 3, "max_retries": 2}  # attempt > max_retries
            
            decision = self.llm.resolve_failover_decision(error, attempt_state)
            
            assert decision.action == "surface_error"
            assert decision.reason == "unknown"


class TestErrorSubclassTyping:
    """Test that error subclasses properly accept and forward error_category."""
    
    def test_llm_error_with_category(self):
        """Test LLMError accepts and forwards error_category."""
        error = LLMError(
            "Model failure", 
            model_name="gpt-4", 
            error_category="rate_limit"
        )
        
        assert error.error_category == "rate_limit"
        assert error.model_name == "gpt-4"
        assert error.is_retryable is False
    
    def test_network_error_with_category(self):
        """Test NetworkError accepts and forwards error_category."""
        error = NetworkError(
            "Connection failed",
            service_name="openai",
            status_code=503,
            error_category="overloaded"
        )
        
        assert error.error_category == "overloaded"
        assert error.service_name == "openai"
        assert error.status_code == 503
    
    def test_tool_execution_error_with_category(self):
        """Test ToolExecutionError accepts and forwards error_category."""
        error = ToolExecutionError(
            "Tool failed",
            tool_name="web_search",
            error_category="auth"
        )
        
        assert error.error_category == "auth"
        assert error.tool_name == "web_search"
        assert error.is_retryable is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])