"""
Message Sanitization - Clean surrogate/non-ASCII characters before LLM calls.

Prevents Unicode encoding issues that can cause silent failures with some
providers when processing emoji, non-Latin text, or corrupted Unicode.
"""

import re
from typing import List, Dict, Any, Union

__all__ = ["sanitize_messages", "strip_surrogates"]


def strip_surrogates(text: str) -> str:
    """Remove surrogate pairs and malformed Unicode from text.
    
    Surrogate pairs (U+D800-U+DFFF) are used in UTF-16 encoding but are
    invalid in UTF-8/Unicode strings. They can appear from:
    - Incorrect Unicode conversion
    - Corrupted text data  
    - Invalid emoji/character sequences
    
    Args:
        text: Input text potentially containing surrogates
        
    Returns:
        Text with surrogates removed or replaced
        
    Examples:
        >>> strip_surrogates("Hello \\uD83D World")  # Missing low surrogate
        'Hello  World'
        >>> strip_surrogates("Valid text 🌍")
        'Valid text 🌍'
    """
    if not text:
        return text
    
    try:
        # Method 1: Encode with surrogatepass, decode with ignore
        # This converts surrogates to UTF-16, then back to UTF-8 safely
        return text.encode('utf-16', 'surrogatepass').decode('utf-16', 'ignore')
    except (UnicodeError, LookupError):
        # Fallback: Remove surrogate code points directly
        return re.sub(r'[\uD800-\uDFFF]', '', text)


def _sanitize_value_recursive(value: Any) -> tuple[Any, bool]:
    """Recursively sanitize any nested string values in a data structure.
    
    Args:
        value: Value to sanitize (can be dict, list, str, or other)
        
    Returns:
        Tuple of (sanitized_value, changed_flag)
    """
    if isinstance(value, str):
        sanitized = strip_surrogates(value)
        return sanitized, sanitized != value
    
    elif isinstance(value, list):
        changed = False
        sanitized_items = []
        for item in value:
            sanitized_item, item_changed = _sanitize_value_recursive(item)
            sanitized_items.append(sanitized_item)
            changed = changed or item_changed
        return sanitized_items, changed
    
    elif isinstance(value, dict):
        changed = False
        sanitized_dict = {}
        for key, nested_value in value.items():
            # Sanitize the key if it's a string
            if isinstance(key, str):
                sanitized_key = strip_surrogates(key)
                if sanitized_key != key:
                    changed = True
                    key = sanitized_key
            
            # Recursively sanitize the value
            sanitized_value, value_changed = _sanitize_value_recursive(nested_value)
            sanitized_dict[key] = sanitized_value
            changed = changed or value_changed
        return sanitized_dict, changed
    
    else:
        # Return other types unchanged
        return value, False


def sanitize_messages(messages: List[Dict[str, Any]]) -> bool:
    """Sanitize message content in-place, removing problematic Unicode.
    
    Processes all string content in message dictionaries, including:
    - message.content (string or list)  
    - message.name
    - Any nested string values (including tool_calls[].function.arguments)
    
    Args:
        messages: List of message dicts to sanitize in-place
        
    Returns:
        True if any changes were made, False otherwise
        
    Examples:
        >>> messages = [{"content": "Hello \\uD83D World", "role": "user"}]
        >>> changed = sanitize_messages(messages)
        >>> assert changed == True
        >>> assert messages[0]["content"] == "Hello  World"
    """
    if not messages:
        return False
    
    changed = False
    
    for message in messages:
        if not isinstance(message, dict):
            continue
            
        # Recursively sanitize the entire message structure
        sanitized_message, message_changed = _sanitize_value_recursive(message)
        if message_changed:
            message.clear()
            message.update(sanitized_message)
            changed = True
    
    return changed


def sanitize_text(text: Union[str, None]) -> Union[str, None]:
    """Sanitize a single text string.
    
    Convenience function for sanitizing individual strings.
    
    Args:
        text: Text to sanitize, or None
        
    Returns:
        Sanitized text, or None if input was None
    """
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    return strip_surrogates(text)
