"""
Redaction utilities for action trace.

Provides deterministic redaction of sensitive data in tool arguments
and results. Uses only stdlib for zero dependencies.
"""

from typing import Any, Dict, Optional, Set
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


# ────────────────────────────────────────────────────────────────────────────
# C7 — PII redaction for LLM egress (opt-in BEFORE_LLM middleware)
# ────────────────────────────────────────────────────────────────────────────

# Additional value-pattern rules for strings that look like secrets
# even when no key=value pair surrounds them.
_VALUE_PATTERNS = (
    # OpenAI-style API keys
    (re.compile(r"\bsk-[A-Za-z0-9]{12,}\b"), "[REDACTED]"),
    # US SSN
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED-SSN]"),
    # Credit card (13-19 digits, loose)
    (re.compile(r"\b(?:\d[ -]?){13,19}\b"), "[REDACTED-CC]"),
    # Email (optional — often safe, but default-scrub for compliance)
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED-EMAIL]"),
)


def scrub_pii_text(text: str) -> str:
    """Redact API keys, passwords, SSNs, credit cards, and emails from free text.

    Reuses REDACT_KEYS for ``key=value`` pairs and adds value-pattern rules
    for naked secrets. Zero dependency (stdlib re only).

    Args:
        text: Input string — returned unchanged if empty or None.

    Returns:
        Scrubbed string with literal secrets replaced by ``[REDACTED*]``.
    """
    if not text:
        return text
    result = redact_string(text, enabled=True)
    for pat, repl in _VALUE_PATTERNS:
        result = pat.sub(repl, result)
    return result


# Module-level state for idempotent enable/disable
_PII_HOOK_ID: Optional[str] = None


def _pii_before_llm_hook(event_data):
    """BEFORE_LLM hook that scrubs every message's content in-place."""
    try:
        messages = getattr(event_data, "messages", None) or []
        modified = []
        for m in messages:
            if isinstance(m, dict) and isinstance(m.get("content"), str):
                m = {**m, "content": scrub_pii_text(m["content"])}
            modified.append(m)
        # Import locally to avoid module-level hooks dep (keeps redact.py lightweight)
        from ..hooks.types import HookResult
        return HookResult(decision="allow", modified_input={"messages": modified})
    except Exception:
        # Never block the LLM call on a scrubber bug
        from ..hooks.types import HookResult
        return HookResult(decision="allow")


def enable_pii_redaction() -> str:
    """Register a BEFORE_LLM hook that scrubs secrets from every message.

    Idempotent — calling twice leaves exactly one hook registered.

    Returns:
        The hook id (useful for :func:`disable_pii_redaction`).
    """
    global _PII_HOOK_ID
    if _PII_HOOK_ID is not None:
        return _PII_HOOK_ID
    from ..hooks.registry import get_default_registry
    from ..hooks.types import HookEvent
    reg = get_default_registry()
    _PII_HOOK_ID = reg.register_function(
        event=HookEvent.BEFORE_LLM,
        func=_pii_before_llm_hook,
        name="praisonaiagents.pii_redactor",
    )
    return _PII_HOOK_ID


def disable_pii_redaction() -> bool:
    """Unregister the PII-redaction hook. No-op if never enabled."""
    global _PII_HOOK_ID
    if _PII_HOOK_ID is None:
        return False
    from ..hooks.registry import get_default_registry
    reg = get_default_registry()
    try:
        reg.unregister(_PII_HOOK_ID)
    finally:
        _PII_HOOK_ID = None
    return True


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
