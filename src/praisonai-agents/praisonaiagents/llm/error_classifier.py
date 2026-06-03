"""
Error Classification - Multi-category error classifier for intelligent retry logic.

Extends the existing single-category rate limit detection with comprehensive
error classification for better handling of different failure modes.

Provides both legacy API (classify_error) and new structured classification
(classify_llm_error) with explicit recovery routing hints.
"""

import re
import random
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple, List, Optional

__all__ = [
    "ErrorCategory",
    "LLMErrorClassification", 
    "classify_error", 
    "classify_llm_error",
    "should_retry", 
    "get_retry_delay",
    "extract_retry_after",
    "get_error_context",
]


class ErrorCategory(str, Enum):
    """Categories of LLM provider errors for intelligent handling."""
    RATE_LIMIT = "rate_limit"           # Too many requests, temporary
    CONTEXT_LIMIT = "context_limit"     # Input too long, need compression
    AUTH = "auth"                       # Authentication/authorization failure  
    INVALID_REQUEST = "invalid_request" # Malformed request, permanent
    TRANSIENT = "transient"            # Network/server issues, temporary
    PERMANENT = "permanent"            # Unrecoverable error


@dataclass
class LLMErrorClassification:
    """
    Structured result of LLM error classification with explicit recovery hints.
    
    This replaces the simple `is_retryable: bool` with actionable recovery routing
    that allows the agent to take specific recovery actions beyond simple retry.
    """
    error_category: str           # "rate_limit" | "context_overflow" | "auth" | "overloaded" | ...
    is_retryable: bool
    should_compress_context: bool # True on context overflow → trigger compaction then retry
    should_rotate_credential: bool
    should_fallback_model: bool   # True when primary model is unavailable
    backoff_seconds: float        # 0 = no wait; >0 = jittered delay before retry
    user_message: str             # Human-readable hint for the end user


# Error patterns for classification (case-insensitive)
_ERROR_PATTERNS: Dict[ErrorCategory, List[str]] = {
    ErrorCategory.RATE_LIMIT: [
        r"rate.?limit",
        r"429",
        r"too.?many.?request",
        r"resource.?exhausted", 
        r"quota.?exceeded",
        r"tokens.?per.?minute",
        r"requests.?per.?minute",
        r"concurrent.?requests",
    ],
    
    ErrorCategory.CONTEXT_LIMIT: [
        r"context.?length",
        r"maximum.?context", 
        r"token.?limit",
        r"input.?too.?long",
        r"sequence.?too.?long",
        r"context.?window",
        r"413",  # Request Entity Too Large
        r"payload.?too.?large",
    ],
    
    ErrorCategory.AUTH: [
        r"authenticat",
        r"authoriz",
        r"401", 
        r"403",
        r"invalid.?api.?key",
        r"api.?key.*invalid",
        r"permission.?denied", 
        r"access.?denied",
        r"forbidden",
        r"unauthorized",
        r"invalid.?token",
        r"expired.*token",
    ],
    
    ErrorCategory.INVALID_REQUEST: [
        r"invalid.*request",
        r"bad.?request",
        r"400",
        r"malformed",
        r"invalid.*parameter",
        r"unsupported.*model",
        r"model.*not.*found",
        r"validation.*error",
        r"schema.*error",
    ],
    
    ErrorCategory.TRANSIENT: [
        r"timeout",
        r"timed.?out",
        r"500", r"502", r"503", r"504",
        r"internal.?server.?error",
        r"bad.?gateway", 
        r"service.?unavailable",
        r"gateway.?timeout",
        r"connection.*error",
        r"network.*error",
        r"temporary.*unavailable",
        r"server.?overload",
        r"retry.?after",
    ],
}


def classify_llm_error(
    exc: Exception,
    *,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    context_length: int = 0,
    retry_depth: int = 0,
) -> LLMErrorClassification:
    """
    Classify an LLM error and return structured recovery hints.
    
    This is the enhanced error classifier that provides explicit recovery routing
    beyond simple retry/no-retry decisions.
    
    Args:
        exc: The original exception from the LLM API call
        provider: LLM provider name (e.g., "openai", "anthropic", "azure")
        model: Model name (e.g., "gpt-4", "claude-3-sonnet")
        prompt_tokens: Current prompt token count
        context_length: Current context window usage
        retry_depth: Current retry attempt (0-based)
        
    Returns:
        LLMErrorClassification with specific recovery routing
    """
    from .retry_utils import jittered_backoff
    
    error_str = str(exc).lower()
    
    # Use existing classification as base
    category = classify_error(exc)
    
    # Rate limit classification
    if category == ErrorCategory.RATE_LIMIT:
        retry_after = extract_retry_after(exc)
        if retry_after:
            from .retry_utils import calculate_backoff_with_retry_after
            backoff_time = calculate_backoff_with_retry_after(retry_after, retry_depth + 1)
        else:
            backoff_time = _calculate_rate_limit_backoff(error_str, provider, retry_depth + 1)
        
        return LLMErrorClassification(
            error_category="rate_limit",
            is_retryable=True,
            should_compress_context=False,
            should_rotate_credential=False,
            should_fallback_model=False,
            backoff_seconds=backoff_time,
            user_message=f"Rate limit exceeded for {provider}. Retrying with exponential backoff.",
        )
    
    # Context overflow classification  
    if category == ErrorCategory.CONTEXT_LIMIT:
        return LLMErrorClassification(
            error_category="context_overflow",
            is_retryable=True,
            should_compress_context=True,
            should_rotate_credential=False,
            should_fallback_model=False,
            backoff_seconds=0.0,
            user_message=f"Context window exceeded for {model}. Compressing context and retrying.",
        )
    
    # Authentication/authorization errors
    if category == ErrorCategory.AUTH:
        return LLMErrorClassification(
            error_category="auth",
            is_retryable=False,  # Don't retry until credential rotation is implemented
            should_compress_context=False,
            should_rotate_credential=True,
            should_fallback_model=False,
            backoff_seconds=0.0,
            user_message=f"Authentication failed for {provider}. Check API credentials.",
        )
    
    # Transient service errors (map to overloaded category for consistency with issue)
    if category == ErrorCategory.TRANSIENT:
        return LLMErrorClassification(
            error_category="overloaded",
            is_retryable=True,
            should_compress_context=False,
            should_rotate_credential=False,
            should_fallback_model=True,
            backoff_seconds=_calculate_service_backoff(error_str, retry_depth + 1),
            user_message=f"Service {provider} temporarily unavailable. Falling back to alternate model.",
        )
    
    # Invalid request errors (generally not retryable)
    if category == ErrorCategory.INVALID_REQUEST:
        return LLMErrorClassification(
            error_category="model_error",
            is_retryable=False,
            should_compress_context=False,
            should_rotate_credential=False,
            should_fallback_model=False,
            backoff_seconds=0.0,
            user_message=f"Model {model} returned an error. Check your request parameters.",
        )
    
    # Permanent errors
    if category == ErrorCategory.PERMANENT:
        return LLMErrorClassification(
            error_category="permanent",
            is_retryable=False,
            should_compress_context=False,
            should_rotate_credential=False,
            should_fallback_model=False,
            backoff_seconds=0.0,
            user_message="Permanent error occurred. Cannot retry.",
        )
    
    # This fallback should be unreachable since classify_error() always returns one of the 6 categories
    # But we keep it for safety in case of future enum additions
    return LLMErrorClassification(
        error_category="unknown",
        is_retryable=True,
        should_compress_context=False,
        should_rotate_credential=False,
        should_fallback_model=False,
        backoff_seconds=jittered_backoff(retry_depth + 1, base=2.0),
        user_message="Unknown error occurred. Retrying with backoff.",
    )


def _calculate_rate_limit_backoff(error_str: str, provider: str, retry_attempt: int = 1) -> float:
    """Calculate jittered backoff time for rate limits based on provider and attempt."""
    from .retry_utils import jittered_backoff
    
    # Provider-specific base delays
    if provider == "openai":
        base = 60.0  # OpenAI rate limits are typically per minute
    elif provider == "anthropic":
        base = 20.0  # Anthropic rate limits are often shorter
    elif provider == "azure":
        base = 45.0  # Azure varies by deployment
    else:
        base = 30.0  # Default backoff
    
    # Apply jittered exponential backoff
    return jittered_backoff(retry_attempt, base=base)


def _calculate_service_backoff(error_str: str, retry_attempt: int = 1) -> float:
    """Calculate jittered backoff time for service unavailable errors."""
    from .retry_utils import jittered_backoff
    
    # Look for any suggested retry time in error message
    retry_match = re.search(r'retry[:\s]+(\d+)', error_str)
    if retry_match:
        suggested_delay = min(float(retry_match.group(1)), 120.0)  # Cap at 2 minutes
        # Use the larger of suggested delay or jittered backoff
        jittered_delay = jittered_backoff(retry_attempt, base=15.0)
        return max(suggested_delay, jittered_delay)
    
    # Default jittered service unavailable backoff
    return jittered_backoff(retry_attempt, base=15.0)


def classify_error(error: Exception) -> ErrorCategory:
    """Classify an error into a category for intelligent handling.
    
    Args:
        error: Exception to classify
        
    Returns:
        ErrorCategory indicating how the error should be handled
        
    Examples:
        >>> classify_error(Exception("Rate limit exceeded"))
        ErrorCategory.RATE_LIMIT
        >>> classify_error(Exception("Context length 8192 exceeded"))  
        ErrorCategory.CONTEXT_LIMIT
        >>> classify_error(Exception("Invalid API key"))
        ErrorCategory.AUTH
    """
    error_text = f"{type(error).__name__} {error}".lower()
    
    # Check each category's patterns
    for category, patterns in _ERROR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                return category
    
    # Default to permanent for unknown errors
    return ErrorCategory.PERMANENT


def should_retry(category: ErrorCategory) -> bool:
    """Determine if an error category should be retried.
    
    Args:
        category: Error category from classify_error()
        
    Returns:
        True if the error type should be retried
    """
    return category in {
        ErrorCategory.RATE_LIMIT,
        ErrorCategory.CONTEXT_LIMIT,  # Could retry with compression
        ErrorCategory.TRANSIENT,
    }


def get_retry_delay(category: ErrorCategory, attempt: int = 1, base_delay: float = 1.0) -> float:
    """Get the appropriate delay before retrying based on error category.
    
    Uses full jitter to prevent thundering herd problems in multi-agent setups
    where multiple agents hit rate limits simultaneously.
    
    Args:
        category: Error category
        attempt: Current attempt number (1-based)
        base_delay: Base delay in seconds
        
    Returns:
        Delay in seconds, or 0 if should not retry
        
    Examples:
        >>> # With jitter, these will return random values in range:
        >>> get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=1)  # 0.0 to 3.0
        >>> get_retry_delay(ErrorCategory.TRANSIENT, attempt=3)   # 0.0 to 8.0
        >>> get_retry_delay(ErrorCategory.AUTH, attempt=1)        # Always 0
    """
    attempt = max(1, attempt)

    if not should_retry(category):
        return 0
    
    if category == ErrorCategory.RATE_LIMIT:
        # Exponential backoff with equal jitter for rate limits (minimum floor to prevent instant retries)
        max_delay = min(base_delay * (3 ** attempt), 60.0)
        return base_delay + random.uniform(0, max_delay - base_delay)
    
    elif category == ErrorCategory.CONTEXT_LIMIT:
        # Short delay for context limits (no jitter needed - not a contention issue)
        return base_delay * 0.5
    
    elif category == ErrorCategory.TRANSIENT:
        # Exponential backoff with equal jitter for transient errors (minimum floor to prevent instant retries)
        max_delay = min(base_delay * (2 ** attempt), 30.0)
        return base_delay + random.uniform(0, max_delay - base_delay)
    
    return 0


def extract_retry_after(error: Exception) -> Optional[float]:
    """Extract Retry-After header value from rate limit errors.
    
    Args:
        error: Exception potentially containing Retry-After info
        
    Returns:
        Delay in seconds if found, None otherwise
    """
    error_str = str(error)
    
    # Look for common Retry-After patterns
    patterns = [
        r"retry.?after[:\s]+(\d+)",
        r"retry[:\s]+(\d+)",
        r"wait[:\s]+(\d+)",
        r"(\d+).*second",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, error_str, re.IGNORECASE)
        if match:
            try:
                delay = float(match.group(1))
                return min(delay, 300.0)  # Cap at 5 minutes
            except (ValueError, IndexError):
                continue
    
    return None


def get_error_context(error: Exception) -> Dict[str, str]:
    """Extract structured context from an error for logging/debugging.
    
    Args:
        error: Exception to analyze
        
    Returns:
        Dictionary with error context information
    """
    category = classify_error(error)
    
    context = {
        "error_type": type(error).__name__,
        "category": category.value,
        "should_retry": str(should_retry(category)),
        "message": str(error)[:500],  # Truncate long messages
    }
    
    # Add category-specific context
    if category == ErrorCategory.RATE_LIMIT:
        retry_after = extract_retry_after(error)
        if retry_after:
            context["retry_after"] = str(retry_after)
    
    elif category == ErrorCategory.CONTEXT_LIMIT:
        context["suggestion"] = "Try reducing input size or enabling compression"
        
    elif category == ErrorCategory.AUTH:
        context["suggestion"] = "Check API key configuration"
    
    elif category == ErrorCategory.INVALID_REQUEST:
        context["suggestion"] = "Review request parameters"
        
    return context
