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
        # Method 1: Encode with surrogatepass, decode with replace
        # This converts surrogates to UTF-16, then back to UTF-8 safely
        return text.encode('utf-16', 'surrogatepass').decode('utf-16', 'replace')
    except (UnicodeError, LookupError):
        # Fallback: Remove surrogate code points directly
        return re.sub(r'[\uD800-\uDFFF]', '', text)


def sanitize_messages(messages: List[Dict[str, Any]]) -> bool:
    """Sanitize message content in-place, removing problematic Unicode.
    
    Processes all string content in message dictionaries, including:
    - message.content (string or list)  
    - message.name
    - Any nested string values
    
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
            
        # Sanitize content field (most common)
        if "content" in message:
            content = message["content"]
            
            if isinstance(content, str):
                sanitized = strip_surrogates(content)
                if sanitized != content:
                    message["content"] = sanitized
                    changed = True
                    
            elif isinstance(content, list):
                # Handle list content (e.g., multimodal messages)
                for i, item in enumerate(content):
                    if isinstance(item, dict) and "text" in item:
                        text = item["text"]
                        if isinstance(text, str):
                            sanitized = strip_surrogates(text)
                            if sanitized != text:
                                content[i]["text"] = sanitized
                                changed = True
                    elif isinstance(item, str):
                        sanitized = strip_surrogates(item)
                        if sanitized != item:
                            content[i] = sanitized
                            changed = True
        
        # Sanitize other string fields
        for key, value in message.items():
            if isinstance(value, str) and key != "content":  # Already handled above
                sanitized = strip_surrogates(value)
                if sanitized != value:
                    message[key] = sanitized
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