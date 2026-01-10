"""
Development utilities for PraisonAI.

This module contains development-only tools that are NOT imported during normal runtime.
"""

__all__ = ["generate_api_md", "ApiMdGenerator"]


def __getattr__(name: str):
    """Lazy load development utilities."""
    if name in ("generate_api_md", "ApiMdGenerator"):
        from .api_md import generate_api_md, ApiMdGenerator
        if name == "generate_api_md":
            return generate_api_md
        return ApiMdGenerator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
