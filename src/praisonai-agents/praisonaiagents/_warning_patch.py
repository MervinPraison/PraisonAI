"""
Minimal warning patch to suppress specific third-party warnings.
This module patches the warnings module to intercept specific messages.
"""

import warnings
import functools
import sys

# Apply aggressive warning filters first
warnings.filterwarnings("ignore", message=".*There is no current event loop.*", category=DeprecationWarning)
warnings.filterwarnings("ignore", message=".*Pydantic serializer warnings.*")
warnings.filterwarnings("ignore", message=".*PydanticSerializationUnexpectedValue.*")
warnings.filterwarnings("ignore", message=".*Expected \\d+ fields but got.*")
warnings.filterwarnings("ignore", message=".*Expected `StreamingChoices` but got.*")
warnings.filterwarnings("ignore", message=".*serialized value may not be as expected.*")
warnings.filterwarnings("ignore", message=".*Use 'content=<...>' to upload raw bytes/text content.*")
warnings.filterwarnings("ignore", message=".*The `dict` method is deprecated.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")

# Store the original warn function
_original_warn = warnings.warn
_original_warn_explicit = warnings.warn_explicit

# Messages to suppress (partial matches)
SUPPRESSED_PATTERNS = [
    "Use 'content=<...>' to upload raw bytes/text content",
    "The `dict` method is deprecated; use `model_dump` instead",
    "Pydantic serializer warnings",
    "PydanticSerializationUnexpectedValue",
    "Expected",  # Catches all "Expected N fields but got M" patterns
    "Expected `StreamingChoices` but got `Choices`",
    "serialized value may not be as expected",
    "Mixing V1 models and V2 models",
    "Please upgrade `Settings` to V2",
    "There is no current event loop"
]

@functools.wraps(_original_warn)
def _patched_warn(message, category=None, stacklevel=1, source=None):
    """Patched warn function that suppresses specific messages."""
    msg_str = str(message)
    
    for pattern in SUPPRESSED_PATTERNS:
        if pattern in msg_str:
            return
    
    if category is UserWarning and "pydantic" in msg_str.lower():
        return
    
    _original_warn(message, category, stacklevel, source)

@functools.wraps(_original_warn_explicit)
def _patched_warn_explicit(message, category, filename, lineno, module=None, registry=None, module_globals=None, source=None):
    """Patched warn_explicit function that suppresses specific messages."""
    msg_str = str(message)
    
    for pattern in SUPPRESSED_PATTERNS:
        if pattern in msg_str:
            return
    
    if category is UserWarning and "pydantic" in msg_str.lower():
        return
    
    if module and "pydantic" in str(module):
        return
        
    _original_warn_explicit(message, category, filename, lineno, module, registry, module_globals, source)

# Apply the patches
warnings.warn = _patched_warn
warnings.warn_explicit = _patched_warn_explicit

# Also patch sys.modules warnings if it exists
if 'warnings' in sys.modules:
    sys.modules['warnings'].warn = _patched_warn
    sys.modules['warnings'].warn_explicit = _patched_warn_explicit