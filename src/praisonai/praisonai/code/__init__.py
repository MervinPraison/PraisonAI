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

from importlib import import_module as _import_module


_EXPORT_MODULES = {
    # Main tools (low-level)
    "read_file": ".tools",
    "write_file": ".tools",
    "list_files": ".tools",
    "apply_diff": ".tools",
    "search_replace": ".tools",
    "execute_command": ".tools",
    # Agent tools (high-level, string returns)
    "set_workspace": ".agent_tools",
    "get_workspace": ".agent_tools",
    "code_read_file": ".agent_tools",
    "code_write_file": ".agent_tools",
    "code_list_files": ".agent_tools",
    "code_apply_diff": ".agent_tools",
    "code_search_replace": ".agent_tools",
    "code_execute_command": ".agent_tools",
    "CODE_TOOLS": ".agent_tools",
    "create_diff_block": ".agent_tools",
    "create_multi_diff": ".agent_tools",
    # Diff utilities
    "DiffResult": ".diff",
    "apply_search_replace_diff": ".diff",
    "parse_diff_blocks": ".diff",
    # Utilities
    "FileAccessController": ".utils",
    "add_line_numbers": ".utils",
    "strip_line_numbers": ".utils",
}

__all__ = list(_EXPORT_MODULES)
__version__ = "0.1.0"


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(_import_module(module_name, __name__), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()).union(__all__))
