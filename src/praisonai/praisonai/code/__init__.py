"""
PraisonAI Code - AI-powered code editing tools.

This module provides tools for AI agents to read, write, and modify code files
with precision using search/replace diff strategies similar to Kilo Code.

Features:
- read_file: Read file contents with optional line ranges
- write_file: Create or overwrite files
- list_files: List directory contents with filtering
- apply_diff: Apply SEARCH/REPLACE diffs with fuzzy matching
- search_replace: Multiple search/replace operations
- execute_command: Run shell commands safely

Example:
    from praisonai.code import read_file, write_file, apply_diff
    
    # Read a file
    content = read_file("path/to/file.py")
    
    # Write a file
    write_file("path/to/new_file.py", "print('hello')")
    
    # Apply a diff
    result = apply_diff("path/to/file.py", diff_content)
"""

from .tools import (
    read_file,
    write_file,
    list_files,
    apply_diff,
    search_replace,
    execute_command,
)

from .diff import (
    DiffResult,
    apply_search_replace_diff,
    parse_diff_blocks,
)

from .utils import (
    FileAccessController,
    add_line_numbers,
    strip_line_numbers,
)

from .agent_tools import (
    set_workspace,
    get_workspace,
    code_read_file,
    code_write_file,
    code_list_files,
    code_apply_diff,
    code_search_replace,
    code_execute_command,
    CODE_TOOLS,
    create_diff_block,
    create_multi_diff,
)

__all__ = [
    # Main tools (low-level)
    "read_file",
    "write_file", 
    "list_files",
    "apply_diff",
    "search_replace",
    "execute_command",
    # Agent tools (high-level, string returns)
    "set_workspace",
    "get_workspace",
    "code_read_file",
    "code_write_file",
    "code_list_files",
    "code_apply_diff",
    "code_search_replace",
    "code_execute_command",
    "CODE_TOOLS",
    "create_diff_block",
    "create_multi_diff",
    # Diff utilities
    "DiffResult",
    "apply_search_replace_diff",
    "parse_diff_blocks",
    # Utilities
    "FileAccessController",
    "add_line_numbers",
    "strip_line_numbers",
]

__version__ = "0.1.0"
