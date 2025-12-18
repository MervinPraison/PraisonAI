"""
Utility functions for PraisonAI Code module.
"""

from .file_utils import (
    add_line_numbers,
    strip_line_numbers,
    every_line_has_line_numbers,
    normalize_line_endings,
    get_file_extension,
    is_binary_file,
    create_directories_for_file,
    file_exists,
)

from .text_utils import (
    normalize_string,
    unescape_html_entities,
    get_similarity,
)

from .ignore_utils import (
    FileAccessController,
    load_gitignore_patterns,
    should_ignore_path,
)

__all__ = [
    # File utilities
    "add_line_numbers",
    "strip_line_numbers",
    "every_line_has_line_numbers",
    "normalize_line_endings",
    "get_file_extension",
    "is_binary_file",
    "create_directories_for_file",
    "file_exists",
    # Text utilities
    "normalize_string",
    "unescape_html_entities",
    "get_similarity",
    # Ignore utilities
    "FileAccessController",
    "load_gitignore_patterns",
    "should_ignore_path",
]
