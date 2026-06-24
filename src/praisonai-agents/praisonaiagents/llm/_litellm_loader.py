"""
Shared lazy-import helper for the optional litellm dependency.

This centralizes the "import litellm at most once, then cache the result
(None if unavailable)" pattern used across the llm/ package so the lazy-loading
behaviour is expressed in a single place.

litellm remains an optional dependency and is never imported at module level.
"""

# Module-level cache for litellm (lazy loaded)
_litellm_module = None
_litellm_import_attempted = False


def get_litellm(on_missing=None):
    """
    Lazy import litellm module.

    Returns the litellm module if available, None otherwise.
    Caches the result to avoid repeated import attempts.

    Args:
        on_missing: Optional callable invoked (with no arguments) when litellm
            cannot be imported. Useful for logging. It is invoked on every call
            that finds litellm unavailable (including cached failures), so each
            caller's diagnostics are honoured regardless of call ordering.

    Returns:
        The litellm module if importable, otherwise None.
    """
    global _litellm_module, _litellm_import_attempted

    if not _litellm_import_attempted:
        _litellm_import_attempted = True
        try:
            import litellm
            _litellm_module = litellm
        except ImportError:
            _litellm_module = None

    if _litellm_module is None and on_missing is not None:
        on_missing()

    return _litellm_module
