"""
Unicode safety utilities for gateway server on Windows.

Provides safe error message formatting for bot error handlers that may
receive exception text containing Unicode characters that cannot be encoded
with Windows cp1252 default encoding.
"""

import logging
import re
import unicodedata
from typing import Union, Any

logger = logging.getLogger(__name__)

# Module-level constants to avoid recreation on every call
_SYMBOL_MAP: dict = {
    '\u26a0': '!',      # WARNING SIGN -> !
    '\u2713': 'OK',     # CHECK MARK -> OK
    '\u2717': 'X',      # BALLOT X -> X
    '\u2192': '->',     # RIGHT ARROW -> ->
    '\u2190': '<-',     # LEFT ARROW -> <-
    '\u2022': '*',      # BULLET -> *
    '\u00ae': '(R)',    # REGISTERED SIGN -> (R)
    '\u00a9': '(C)',    # COPYRIGHT SIGN -> (C)
    '\u2026': '...',    # HORIZONTAL ELLIPSIS -> ...
    '\u201c': '"',      # LEFT DOUBLE QUOTATION MARK -> "
    '\u201d': '"',      # RIGHT DOUBLE QUOTATION MARK -> "
    '\u2018': "'",      # LEFT SINGLE QUOTATION MARK -> '
    '\u2019': "'",      # RIGHT SINGLE QUOTATION MARK -> '
    '\u2013': '-',      # EN DASH -> -
    '\u2014': '--',     # EM DASH -> --
}

_LATIN1_MAP: dict = {
    '\u00e0': 'a', '\u00e1': 'a', '\u00e2': 'a', '\u00e3': 'a',
    '\u00e4': 'a', '\u00e5': 'a',
    '\u00e8': 'e', '\u00e9': 'e', '\u00ea': 'e', '\u00eb': 'e',
    '\u00ec': 'i', '\u00ed': 'i', '\u00ee': 'i', '\u00ef': 'i',
    '\u00f2': 'o', '\u00f3': 'o', '\u00f4': 'o', '\u00f5': 'o', '\u00f6': 'o',
    '\u00f9': 'u', '\u00fa': 'u', '\u00fb': 'u', '\u00fc': 'u',
    '\u00e7': 'c', '\u00f1': 'n',
    '\u00c0': 'A', '\u00c1': 'A', '\u00c2': 'A', '\u00c3': 'A',
    '\u00c4': 'A', '\u00c5': 'A',
    '\u00c8': 'E', '\u00c9': 'E', '\u00ca': 'E', '\u00cb': 'E',
    '\u00cc': 'I', '\u00cd': 'I', '\u00ce': 'I', '\u00cf': 'I',
    '\u00d2': 'O', '\u00d3': 'O', '\u00d4': 'O', '\u00d5': 'O', '\u00d6': 'O',
    '\u00d9': 'U', '\u00da': 'U', '\u00db': 'U', '\u00dc': 'U',
    '\u00c7': 'C', '\u00d1': 'N',
}

# Pre-compiled regex patterns for API error extraction
_API_PATTERNS = [
    re.compile(r"Error code: (\d+) - (.+)", re.IGNORECASE),  # OpenAI format
    re.compile(r"HTTP (\d+): (.+)", re.IGNORECASE),          # General HTTP error
    re.compile(r"exceeded.*quota", re.IGNORECASE),            # Quota/billing issues
    re.compile(r"insufficient.*quota", re.IGNORECASE),        # Quota/billing issues
    re.compile(r"Rate limit.*exceeded", re.IGNORECASE),       # Rate limiting
    re.compile(r"Authentication.*failed", re.IGNORECASE),     # Auth issues
]


def safe_error_message(exc: Union[BaseException, str, Any], max_len: int = 500) -> str:
    """Create ASCII-safe error text for Telegram/Discord replies on all platforms.

    On Windows, Python's default console encoding is often cp1252 (Windows-1252),
    not UTF-8. When an exception contains non-ASCII characters (warning symbols,
    emoji, international text from LLM output), the error handler can crash with
    a 'charmap' encoding error.

    This function sanitizes exception text to prevent secondary encoding failures
    while preserving the meaning of the original error.

    Args:
        exc: Exception, string, or any object to convert to safe error text
        max_len: Maximum length of returned message

    Returns:
        ASCII-safe error string suitable for bot replies
    """
    if isinstance(exc, BaseException):
        text = str(exc) or type(exc).__name__
    else:
        text = str(exc)

    # Apply specific symbol replacements first to preserve meaning
    for unicode_char, ascii_replacement in _SYMBOL_MAP.items():
        text = text.replace(unicode_char, ascii_replacement)

    # Build ASCII-safe output using module-level maps and NFKD normalization.
    # NFKD decomposes e.g. 'e\u0301' (e + combining accent) so the base
    # letter survives encode('ascii', errors='ignore').
    parts = []
    for char in text:
        if ord(char) < 128:
            parts.append(char)
        elif char in _LATIN1_MAP:
            parts.append(_LATIN1_MAP[char])
        else:
            nfkd = unicodedata.normalize('NFKD', char)
            ascii_base = nfkd.encode('ascii', errors='ignore').decode('ascii')
            parts.append(ascii_base if ascii_base else '?')

    safe_text = ''.join(parts)

    if len(safe_text) > max_len:
        safe_text = safe_text[:max_len - 3] + "..."

    return safe_text.strip() or "Error occurred"


def safe_log_message(exc: Union[BaseException, str, Any]) -> str:
    """Create a safe version of an error message for logging.

    Preserves Unicode for UTF-8-capable log handlers while replacing
    lone surrogates (U+D800-U+DFFF) that cannot be encoded in any standard
    encoding.

    Args:
        exc: Exception, string, or any object to log

    Returns:
        String safe for logging, with lone surrogates replaced by U+FFFD
    """
    if isinstance(exc, BaseException):
        text = str(exc) or type(exc).__name__
    else:
        text = str(exc)

    return text.encode('utf-8', errors='replace').decode('utf-8')


def extract_root_cause_from_error(error_text: str) -> str:
    """Extract the root cause from complex error messages.

    When error chaining occurs (e.g., a charmap error masking an API quota
    error), try to extract the underlying meaningful error for the user.

    The returned string may still contain non-ASCII characters; callers
    should pass it through :func:`safe_error_message` before display.

    Args:
        error_text: Full error message text

    Returns:
        Simplified error message focusing on root cause (may be non-ASCII)
    """
    for pattern in _API_PATTERNS:
        match = pattern.search(error_text)
        if match:
            if len(match.groups()) >= 2:
                return f"Error {match.group(1)}: {match.group(2)}"
            return match.group(0)

    lower = error_text.lower()
    if "quota" in lower:
        return "API quota exceeded. Check billing."
    if "rate limit" in lower:
        return "Rate limit exceeded. Try again later."
    if "authentication" in lower:
        return "Authentication failed. Check API key."
    if "timeout" in lower:
        return "Request timeout. Try again."

    return error_text
