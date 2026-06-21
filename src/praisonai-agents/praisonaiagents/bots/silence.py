"""
Silence protocol for bot gateways.

Provides a canonical contract for agents to signal intentional silence
(no reply) in group/ambient channels. Zero dependencies.
"""

SILENT_REPLY_TOKEN = "NO_REPLY"

_MARKERS = frozenset({"NO_REPLY", "[SILENT]", "SILENT"})


def is_intentional_silence_response(text: str | None) -> bool:
    """Check if a response is an intentional silence signal.
    
    True only when the reply is *exactly* a silence marker (not prose mentioning it).
    Blank/empty responses are NOT treated as deliberate silence.
    
    Args:
        text: The response text to check
        
    Returns:
        True if the response is exactly a silence token, False otherwise
        
    Examples:
        >>> is_intentional_silence_response("NO_REPLY")
        True
        >>> is_intentional_silence_response("[SILENT]")
        True
        >>> is_intentional_silence_response("I think NO_REPLY is good")
        False
        >>> is_intentional_silence_response("")
        False
        >>> is_intentional_silence_response(None)
        False
    """
    if not text:
        return False  # blank != deliberate silence
    return text.strip().strip("[]").upper() in _MARKERS