"""
Diff handling for PraisonAI Code module.

Provides SEARCH/REPLACE diff parsing and application with fuzzy matching.
"""

from .diff_strategy import (
    DiffResult,
    DiffBlock,
    apply_search_replace_diff,
    parse_diff_blocks,
    validate_diff_format,
)

__all__ = [
    "DiffResult",
    "DiffBlock",
    "apply_search_replace_diff",
    "parse_diff_blocks",
    "validate_diff_format",
]
