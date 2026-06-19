# praisonai/cli/_warnings.py
"""Lightweight warning filter support for CLI usage.

This module contains self-contained warning filter functions that were
previously in cli/main.py. Extracted to avoid importing the heavy 7000-line
main.py module (with its yaml/rich/dotenv dependencies) just to set up
warning filters.
"""

import warnings
import atexit

_SUPPRESSED_PATTERNS = (
    "Pydantic serializer warnings",
    "PydanticSerializationUnexpectedValue",
    "Expected ",  # Narrowed from just "Expected" to avoid false positives
    "StreamingChoices",
    "serialized value may not be as expected",
    "duckduckgo_search",
)

_installed = False
_original_showwarning = None
_original_filters = None

def install_warning_filters() -> None:
    """Install PraisonAI's noise filters. Idempotent. CLI-only."""
    global _installed, _original_showwarning, _original_filters
    if _installed:
        return
    _original_showwarning = warnings.showwarning
    _original_filters = list(warnings.filters)

    # Install filterwarnings for common patterns
    for pattern in _SUPPRESSED_PATTERNS:
        warnings.filterwarnings("ignore", message=f".*{pattern}.*")
    warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")

    def _filtered_showwarning(message, category, filename, lineno, file=None, line=None):
        msg_str = str(message)
        if any(pattern in msg_str for pattern in _SUPPRESSED_PATTERNS):
            return
        if category is UserWarning and "pydantic" in filename.lower():
            return
        _original_showwarning(message, category, filename, lineno, file, line)

    warnings.showwarning = _filtered_showwarning
    atexit.register(_uninstall_warning_filters)
    _installed = True

def _uninstall_warning_filters() -> None:
    """Restore original warnings behavior on exit."""
    global _installed, _original_filters, _original_showwarning
    if _installed and _original_showwarning is not None:
        warnings.showwarning = _original_showwarning
        if _original_filters is not None:
            warnings.filters[:] = _original_filters
        _installed = False