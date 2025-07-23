"""
Minimal warning patch to suppress specific third-party warnings.
This module patches the warnings module to intercept specific messages.
"""

import warnings
import functools

# Store the original warn function
_original_warn = warnings.warn

# Messages to suppress
SUPPRESSED_MESSAGES = [
    "Use 'content=<...>' to upload raw bytes/text content",
    "The `dict` method is deprecated; use `model_dump` instead"
]

@functools.wraps(_original_warn)
def _patched_warn(message, category=None, stacklevel=1, source=None):
    """Patched warn function that suppresses specific messages."""
    # Convert message to string for comparison
    msg_str = str(message)
    
    # Check if this message should be suppressed
    for suppressed in SUPPRESSED_MESSAGES:
        if suppressed in msg_str:
            return  # Suppress the warning
    
    # Otherwise, call the original warn function
    _original_warn(message, category, stacklevel, source)

# Apply the patch
warnings.warn = _patched_warn