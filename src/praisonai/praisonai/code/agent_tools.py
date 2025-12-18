"""
Agent-compatible tool wrappers for PraisonAI Code.

These functions are designed to be used as tools with PraisonAI agents.
They return string results suitable for agent consumption.
"""

import os
from typing import Optional

from .tools import (
    read_file as _read_file,
    write_file as _write_file,
    list_files as _list_files,
    apply_diff as _apply_diff,
    search_replace as _search_replace,
    execute_command as _execute_command,
)
from .tools.apply_diff import create_diff_block, create_multi_diff


# Global workspace setting for tools
_workspace_root: Optional[str] = None


def set_workspace(workspace_path: str) -> None:
    """
    Set the workspace root for all code tools.
    
    Args:
        workspace_path: Absolute path to the workspace root
    """
    global _workspace_root
    _workspace_root = os.path.abspath(workspace_path)


def get_workspace() -> Optional[str]:
    """Get the current workspace root."""
    return _workspace_root


def code_read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> str:
    """
    Read the contents of a file.
    
    Use this tool to read source code files. The content is returned with
    line numbers for easy reference when making edits.
    
    Args:
        path: Path to the file (relative to workspace or absolute)
        start_line: First line to read (1-indexed, optional)
        end_line: Last line to read (1-indexed, optional)
        
    Returns:
        File content with line numbers, or error message
        
    Example:
        >>> content = code_read_file("src/main.py")
        >>> content = code_read_file("src/main.py", start_line=10, end_line=50)
    """
    result = _read_file(
        path=path,
        start_line=start_line,
        end_line=end_line,
        add_line_nums=True,
        workspace=_workspace_root,
    )
    
    if result['success']:
        header = f"File: {path}"
        if start_line or end_line:
            header += f" (lines {result['start_line']}-{result['end_line']} of {result['total_lines']})"
        else:
            header += f" ({result['total_lines']} lines)"
        return f"{header}\n\n{result['content']}"
    else:
        return f"Error reading {path}: {result['error']}"


def code_write_file(path: str, content: str) -> str:
    """
    Write content to a file, creating it if it doesn't exist.
    
    Use this tool to create new files or completely replace existing files.
    For partial modifications, use code_apply_diff instead.
    
    Args:
        path: Path to the file (relative to workspace or absolute)
        content: Content to write to the file
        
    Returns:
        Success message or error
        
    Example:
        >>> result = code_write_file("src/new_module.py", "def hello():\\n    print('Hello!')")
    """
    result = _write_file(
        path=path,
        content=content,
        workspace=_workspace_root,
        create_directories=True,
        strip_code_fences=True,
    )
    
    if result['success']:
        action = "Created" if result['created'] else "Updated"
        return f"{action} file: {path} ({result['bytes_written']} bytes)"
    else:
        return f"Error writing {path}: {result['error']}"


def code_list_files(
    path: str = ".",
    recursive: bool = False,
    extensions: Optional[str] = None,
) -> str:
    """
    List files in a directory.
    
    Use this tool to explore the codebase structure.
    
    Args:
        path: Directory path (relative to workspace or absolute)
        recursive: Whether to list recursively
        extensions: Comma-separated list of extensions to filter (e.g., "py,js,ts")
        
    Returns:
        Formatted list of files and directories
        
    Example:
        >>> files = code_list_files("src", recursive=True, extensions="py")
    """
    ext_list = None
    if extensions:
        ext_list = [e.strip() for e in extensions.split(',')]
    
    result = _list_files(
        path=path,
        recursive=recursive,
        workspace=_workspace_root,
        extensions=ext_list,
    )
    
    if result['success']:
        lines = [f"Contents of {path}:"]
        
        # Add directories
        for d in result['directories']:
            lines.append(f"  📁 {d['path']}/")
        
        # Add files
        for f in result['files']:
            size = f.get('size', 0)
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f}KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f}MB"
            lines.append(f"  📄 {f['path']} ({size_str})")
        
        if result.get('truncated'):
            lines.append(f"\n  ... (showing {result['total_count']} items, more available)")
        
        return '\n'.join(lines)
    else:
        return f"Error listing {path}: {result['error']}"


def code_apply_diff(path: str, diff: str) -> str:
    """
    Apply a SEARCH/REPLACE diff to modify a file.
    
    Use this tool for precise, surgical edits to existing files.
    The SEARCH section must match existing content exactly.
    
    Diff Format:
        <<<<<<< SEARCH
        :start_line:N
        -------
        [exact content to find]
        =======
        [new content to replace with]
        >>>>>>> REPLACE
    
    Args:
        path: Path to the file to modify
        diff: The SEARCH/REPLACE diff content
        
    Returns:
        Success message with number of changes, or error details
        
    Example:
        >>> diff = '''<<<<<<< SEARCH
        ... :start_line:10
        ... -------
        ... def old_function():
        ...     pass
        ... =======
        ... def new_function():
        ...     return True
        ... >>>>>>> REPLACE'''
        >>> result = code_apply_diff("src/main.py", diff)
    """
    result = _apply_diff(
        path=path,
        diff=diff,
        workspace=_workspace_root,
        fuzzy_threshold=0.95,  # Allow slight fuzzy matching
    )
    
    if result['success']:
        msg = f"Successfully applied {result['applied_count']} change(s) to {path}"
        if result.get('failed_blocks'):
            msg += f"\nWarning: {len(result['failed_blocks'])} block(s) failed to apply"
        return msg
    else:
        error_msg = f"Error applying diff to {path}: {result['error']}"
        if result.get('failed_blocks'):
            for fb in result['failed_blocks'][:3]:  # Show first 3 failures
                error_msg += f"\n- {fb.get('error', 'Unknown error')}"
        return error_msg


def code_search_replace(
    path: str,
    search: str,
    replace: str,
    is_regex: bool = False,
) -> str:
    """
    Perform a search and replace operation on a file.
    
    Use this for simple text replacements. For complex multi-part edits,
    use code_apply_diff instead.
    
    Args:
        path: Path to the file
        search: Text to search for (or regex pattern if is_regex=True)
        replace: Text to replace with
        is_regex: Whether to treat search as a regex pattern
        
    Returns:
        Success message with replacement count, or error
        
    Example:
        >>> result = code_search_replace("src/main.py", "old_name", "new_name")
    """
    result = _search_replace(
        path=path,
        operations=[{
            'search': search,
            'replace': replace,
            'is_regex': is_regex,
        }],
        workspace=_workspace_root,
    )
    
    if result['success']:
        return f"Replaced {result['total_replacements']} occurrence(s) in {path}"
    else:
        return f"Error: {result['error']}"


def code_execute_command(
    command: str,
    cwd: Optional[str] = None,
) -> str:
    """
    Execute a shell command.
    
    Use this tool to run commands like tests, linters, or build tools.
    
    Args:
        command: The command to execute
        cwd: Working directory (relative to workspace or absolute)
        
    Returns:
        Command output (stdout and stderr)
        
    Example:
        >>> result = code_execute_command("python -m pytest tests/")
        >>> result = code_execute_command("npm test", cwd="frontend")
    """
    work_dir = cwd
    if work_dir and _workspace_root and not os.path.isabs(work_dir):
        work_dir = os.path.join(_workspace_root, work_dir)
    elif not work_dir and _workspace_root:
        work_dir = _workspace_root
    
    result = _execute_command(
        command=command,
        cwd=work_dir,
        timeout=120,
    )
    
    output_parts = []
    
    if result['stdout']:
        output_parts.append(f"stdout:\n{result['stdout']}")
    
    if result['stderr']:
        output_parts.append(f"stderr:\n{result['stderr']}")
    
    if result['success']:
        status = f"Command completed successfully (exit code: {result['exit_code']})"
    else:
        if result.get('error'):
            status = f"Command failed: {result['error']}"
        else:
            status = f"Command failed (exit code: {result['exit_code']})"
    
    output_parts.insert(0, status)
    
    return '\n\n'.join(output_parts)


# Export all agent tools
CODE_TOOLS = [
    code_read_file,
    code_write_file,
    code_list_files,
    code_apply_diff,
    code_search_replace,
    code_execute_command,
]

__all__ = [
    'set_workspace',
    'get_workspace',
    'code_read_file',
    'code_write_file',
    'code_list_files',
    'code_apply_diff',
    'code_search_replace',
    'code_execute_command',
    'CODE_TOOLS',
    'create_diff_block',
    'create_multi_diff',
]
