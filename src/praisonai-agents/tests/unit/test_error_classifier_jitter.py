"""
Test for retry jitter in error classifier (Issue #1553 Gap 2)
"""
import pytest
from praisonaiagents.llm.error_classifier import ErrorCategory, get_retry_delay


def test_rate_limit_jitter():
    """Test that RATE_LIMIT errors use jitter with minimum floor"""
    delays = []
    for _ in range(20):
        delay = get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=1)
        delays.append(delay)
    
    # All delays should be in valid range [base_delay=1.0, max_delay=3.0]
    assert all(1.0 <= delay <= 3.0 for delay in delays), f"Some delays out of range: {delays}"
    
    # Should have some variation (jitter working)
    unique_delays = len(set(delays))
    assert unique_delays >= 5, f"Not enough variation in delays (got {unique_delays} unique out of 20)"
    
    # Should have minimum floor (no zero delays)
    assert all(delay >= 1.0 for delay in delays), f"Some delays below minimum: {min(delays)}"


def test_transient_jitter():
    """Test that TRANSIENT errors use jitter with minimum floor"""
    delays = []
    for _ in range(20):
        delay = get_retry_delay(ErrorCategory.TRANSIENT, attempt=1)
        delays.append(delay)
    
    # All delays should be in valid range [base_delay=1.0, max_delay=2.0]
    assert all(1.0 <= delay <= 2.0 for delay in delays), f"Some delays out of range: {delays}"
    
    # Should have some variation
    unique_delays = len(set(delays))
    assert unique_delays >= 5, f"Not enough variation in delays (got {unique_delays} unique out of 20)"
    
    # Should have minimum floor
    assert all(delay >= 1.0 for delay in delays), f"Some delays below minimum: {min(delays)}"


def test_context_limit_deterministic():
    """Test that CONTEXT_LIMIT delays remain deterministic (no jitter needed)"""
    delay1 = get_retry_delay(ErrorCategory.CONTEXT_LIMIT, attempt=1)
    delay2 = get_retry_delay(ErrorCategory.CONTEXT_LIMIT, attempt=1)
    delay3 = get_retry_delay(ErrorCategory.CONTEXT_LIMIT, attempt=2)
    
    # Context limits should be deterministic
    assert delay1 == delay2, "Context limit delays should be deterministic"
    assert delay1 == 0.5, f"Context limit delay should be 0.5, got {delay1}"
    assert delay3 == 0.5, f"Context limit delay should be 0.5 regardless of attempt, got {delay3}"


def test_exponential_backoff_with_jitter():
    """Test that exponential backoff still works with jitter"""
    # Test increasing attempts for rate limits
    delay_attempt1 = get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=1)  # range: [1.0, 3.0]
    delay_attempt2 = get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=2)  # range: [1.0, 9.0]
    delay_attempt3 = get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=3)  # range: [1.0, 27.0]
    
    # Higher attempts should generally produce higher maximum possible delays
    # (though jitter means specific values may vary)
    assert delay_attempt1 <= 3.0, f"Attempt 1 delay should be <= 3.0, got {delay_attempt1}"
    assert delay_attempt2 <= 9.0, f"Attempt 2 delay should be <= 9.0, got {delay_attempt2}"
    assert delay_attempt3 <= 60.0, f"Attempt 3 delay should be <= 60.0 (capped), got {delay_attempt3}"


def test_no_retry_categories():
    """Test that AUTH and other non-retryable categories return 0"""
    assert get_retry_delay(ErrorCategory.AUTH, attempt=1) == 0
    assert get_retry_delay(ErrorCategory.AUTH, attempt=5) == 0