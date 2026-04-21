"""
Error Classification - Multi-category error classifier for intelligent retry logic.

Extends the existing single-category rate limit detection with comprehensive
error classification for better handling of different failure modes.
"""

import re
from enum import Enum
from typing import Dict, Tuple, List, Optional

__all__ = ["ErrorCategory", "classify_error", "should_retry", "get_retry_delay"]


class ErrorCategory(str, Enum):
    """Categories of LLM provider errors for intelligent handling."""
    RATE_LIMIT = "rate_limit"           # Too many requests, temporary
    CONTEXT_LIMIT = "context_limit"     # Input too long, need compression
    AUTH = "auth"                       # Authentication/authorization failure  
    INVALID_REQUEST = "invalid_request" # Malformed request, permanent
    TRANSIENT = "transient"            # Network/server issues, temporary
    PERMANENT = "permanent"            # Unrecoverable error


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
    
    Args:
        category: Error category
        attempt: Current attempt number (1-based)
        base_delay: Base delay in seconds
        
    Returns:
        Delay in seconds, or 0 if should not retry
        
    Examples:
        >>> get_retry_delay(ErrorCategory.RATE_LIMIT, attempt=1)
        2.0
        >>> get_retry_delay(ErrorCategory.TRANSIENT, attempt=3)
        16.0
        >>> get_retry_delay(ErrorCategory.AUTH, attempt=1)
        0
    """
    if not should_retry(category):
        return 0
    
    if category == ErrorCategory.RATE_LIMIT:
        # Longer delay for rate limits to avoid hitting limits again
        return min(base_delay * (3 ** (attempt - 1)), 60.0)
    
    elif category == ErrorCategory.CONTEXT_LIMIT:
        # Short delay for context limits (compression should be tried)
        return base_delay * 0.5
    
    elif category == ErrorCategory.TRANSIENT:
        # Exponential backoff for transient errors
        return min(base_delay * (2 ** (attempt - 1)), 30.0)
    
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