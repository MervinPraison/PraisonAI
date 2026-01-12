"""
Redaction utilities for action trace.

Provides deterministic redaction of sensitive data in tool arguments
and results. Uses only stdlib for zero dependencies.
"""

from typing import Any, Dict, Set
import re

# Keys that should always be redacted (case-insensitive matching)
REDACT_KEYS: Set[str] = {
    # API keys and tokens
    "api_key",
    "apikey",
    "api-key",
    "secret",
    "secret_key",
    "secretkey",
    "private_key",
    "privatekey",
    # Authentication
    "password",
    "passwd",
    "pwd",
    "token",
    "bearer",
    "authorization",
    "auth",
    "auth_token",
    "access_token",
    "refresh_token",
    # Session and cookies
    "cookie",
    "session",
    "session_id",
    "sessionid",
    "credential",
    "credentials",
    # Database
    "connection_string",
    "connectionstring",
    "database_url",
    "db_url",
    "dburl",
    "db_password",
    "db_pass",
    # Cloud provider specific
    "aws_secret",
    "aws_secret_access_key",
    "azure_key",
    "gcp_key",
    "openai_api_key",
    "anthropic_api_key",
}

# Compiled regex for case-insensitive matching
_REDACT_PATTERN = re.compile(
    r"(" + "|".join(re.escape(k) for k in REDACT_KEYS) + r")",
    re.IGNORECASE
)

REDACTED_VALUE = "[REDACTED]"


def _should_redact(key: str) -> bool:
    """Check if a key should be redacted."""
    # Normalize key for comparison
    normalized = key.lower().replace("-", "_").replace(" ", "_")
    
    # Check exact match first
    if normalized in REDACT_KEYS:
        return True
    
    # Check if any redact key is contained in the normalized key
    for redact_key in REDACT_KEYS:
        if redact_key in normalized:
            return True
    
    return False


def redact_dict(data: Dict[str, Any], enabled: bool = True) -> Dict[str, Any]:
    """
    Redact sensitive values from a dictionary.
    
    Args:
        data: Dictionary to redact
        enabled: If False, returns data unchanged
        
    Returns:
        New dictionary with sensitive values redacted
    """
    if not enabled:
        return data
    
    if not data:
        return {}
    
    return _redact_value(data)


def _redact_value(value: Any) -> Any:
    """Recursively redact sensitive values."""
    if isinstance(value, dict):
        return {k: _redact_key_value(k, v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_redact_value(item) for item in value]
    else:
        return value


def _redact_key_value(key: str, value: Any) -> Any:
    """Redact a value if its key is sensitive."""
    if _should_redact(key):
        return REDACTED_VALUE
    
    # Recursively process nested structures
    return _redact_value(value)


def redact_string(text: str, enabled: bool = True) -> str:
    """
    Redact potential secrets from a string.
    
    This is a best-effort function that looks for common patterns
    like "api_key=xxx" or "password: xxx" in strings.
    
    Args:
        text: String to redact
        enabled: If False, returns text unchanged
        
    Returns:
        String with potential secrets redacted
    """
    if not enabled or not text:
        return text
    
    # Pattern for key=value or key: value
    patterns = [
        (r'(["\']?)(' + '|'.join(re.escape(k) for k in REDACT_KEYS) + r')(["\']?\s*[:=]\s*["\']?)([^"\'\s,}\]]+)', 
         r'\1\2\3[REDACTED]'),
    ]
    
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    return result
