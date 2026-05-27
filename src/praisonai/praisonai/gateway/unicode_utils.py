"""
Unicode safety utilities for gateway server on Windows.

Provides safe error message formatting for bot error handlers that may
receive exception text containing Unicode characters that cannot be encoded
with Windows cp1252 default encoding.
"""

import logging
import re
from typing import Union, Any

logger = logging.getLogger(__name__)


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
    # Convert to string
    if isinstance(exc, BaseException):
        text = str(exc) or type(exc).__name__
    else:
        text = str(exc)
    
    # Strip or replace non-ASCII characters for transport while preserving meaning
    # Replace common Unicode symbols that cause encoding issues
    replacements = {
        '\u26a0': '!',      # ⚠ WARNING SIGN -> !
        '\u2713': 'OK',     # ✓ CHECK MARK -> OK  
        '\u2717': 'X',      # ✗ BALLOT X -> X
        '\u2192': '->',     # → RIGHT ARROW -> ->
        '\u2190': '<-',     # ← LEFT ARROW -> <-
        '\u2022': '*',      # • BULLET -> *
        '\u00ae': '(R)',    # ® REGISTERED SIGN -> (R)
        '\u00a9': '(C)',    # © COPYRIGHT SIGN -> (C)
        '\u2026': '...',    # … HORIZONTAL ELLIPSIS -> ...
        '\u201c': '"',      # " LEFT DOUBLE QUOTATION MARK -> "
        '\u201d': '"',      # " RIGHT DOUBLE QUOTATION MARK -> "
        '\u2018': "'",      # ' LEFT SINGLE QUOTATION MARK -> '
        '\u2019': "'",      # ' RIGHT SINGLE QUOTATION MARK -> '
        '\u2013': '-',      # – EN DASH -> -
        '\u2014': '--',     # — EM DASH -> --
    }
    
    # Apply specific replacements first
    for unicode_char, ascii_replacement in replacements.items():
        text = text.replace(unicode_char, ascii_replacement)
    
    # Replace any remaining non-ASCII characters with safe alternatives
    safe_text = ""
    for char in text:
        if ord(char) < 128:  # ASCII
            safe_text += char
        elif ord(char) < 256:  # Latin-1 range
            # Convert common accented characters to ASCII equivalents
            latin1_replacements = {
                'à': 'a', 'á': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a', 'å': 'a',
                'è': 'e', 'é': 'e', 'ê': 'e', 'ë': 'e',
                'ì': 'i', 'í': 'i', 'î': 'i', 'ï': 'i',
                'ò': 'o', 'ó': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
                'ù': 'u', 'ú': 'u', 'û': 'u', 'ü': 'u',
                'ç': 'c', 'ñ': 'n',
                'À': 'A', 'Á': 'A', 'Â': 'A', 'Ã': 'A', 'Ä': 'A', 'Å': 'A',
                'È': 'E', 'É': 'E', 'Ê': 'E', 'Ë': 'E',
                'Ì': 'I', 'Í': 'I', 'Î': 'I', 'Ï': 'I',
                'Ò': 'O', 'Ó': 'O', 'Ô': 'O', 'Õ': 'O', 'Ö': 'O',
                'Ù': 'U', 'Ú': 'U', 'Û': 'U', 'Ü': 'U',
                'Ç': 'C', 'Ñ': 'N',
            }
            safe_text += latin1_replacements.get(char, '?')
        else:
            # Replace with placeholder for truly problematic characters
            safe_text += "?"
    
    # Truncate if necessary
    if len(safe_text) > max_len:
        safe_text = safe_text[:max_len-3] + "..."
    
    # Ensure it's not empty
    if not safe_text.strip():
        safe_text = "Error occurred"
        
    return safe_text


def safe_log_message(exc: Union[BaseException, str, Any]) -> str:
    """Create a safe version of an error message for logging.
    
    Similar to safe_error_message but preserves more Unicode information
    for logging since logs should support UTF-8.
    
    Args:
        exc: Exception, string, or any object to log
        
    Returns:
        UTF-8 safe string for logging with encoding errors replaced
    """
    if isinstance(exc, BaseException):
        text = str(exc) or type(exc).__name__
    else:
        text = str(exc)
    
    # Use errors='replace' to substitute problematic characters with �
    # This preserves the string structure while avoiding encoding crashes
    try:
        # Try to encode as UTF-8 and decode back to catch encoding issues
        text.encode('utf-8')
        return text
    except UnicodeEncodeError:
        # If there are encoding issues, use safe replacement
        return text.encode('utf-8', errors='replace').decode('utf-8')


def ensure_safe_yaml_load(file_path: str):
    """Load YAML file with explicit UTF-8 encoding.
    
    Ensures YAML configuration files are read with UTF-8 encoding
    rather than the system default (which is cp1252 on Windows).
    
    Args:
        file_path: Path to YAML file to load
        
    Returns:
        Parsed YAML content
        
    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    import yaml
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except UnicodeDecodeError as e:
        logger.warning(f"UTF-8 decode failed for {file_path}, falling back to system encoding: {e}")
        # Fallback to system encoding with error handling
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return yaml.safe_load(f)


def extract_root_cause_from_error(error_text: str) -> str:
    """Extract the root cause from complex error messages.
    
    When error chaining occurs (e.g., charmap error masking API quota error),
    try to extract the underlying meaningful error for the user.
    
    Args:
        error_text: Full error message text
        
    Returns:
        Simplified error message focusing on root cause
    """
    # Look for common API error patterns
    api_patterns = [
        r"Error code: (\d+) - (.+)",  # OpenAI error format
        r"HTTP (\d+): (.+)",          # General HTTP error
        r"exceeded.*quota",           # Quota/billing issues
        r"insufficient.*quota",       # Quota/billing issues
        r"Rate limit.*exceeded",      # Rate limiting
        r"Authentication.*failed",    # Auth issues
    ]
    
    for pattern in api_patterns:
        match = re.search(pattern, error_text, re.IGNORECASE)
        if match:
            if len(match.groups()) >= 2:
                return f"Error {match.group(1)}: {match.group(2)}"
            else:
                return match.group(0)
    
    # Look for specific error types that should be surfaced
    if "quota" in error_text.lower():
        return "API quota exceeded. Check billing."
    if "rate limit" in error_text.lower():
        return "Rate limit exceeded. Try again later."
    if "authentication" in error_text.lower():
        return "Authentication failed. Check API key."
    if "timeout" in error_text.lower():
        return "Request timeout. Try again."
    
    # If no specific patterns match, return the original safe message
    return safe_error_message(error_text)