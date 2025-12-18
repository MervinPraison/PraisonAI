"""
Apply Diff Tool for PraisonAI Code.

Provides functionality to apply SEARCH/REPLACE diffs to files
with fuzzy matching support.
"""

import os
from typing import Optional, Dict, Any

from ..diff.diff_strategy import apply_search_replace_diff
from ..utils.file_utils import (
    file_exists,
    is_path_within_directory,
)


def apply_diff(
    path: str,
    diff: str,
    workspace: Optional[str] = None,
    fuzzy_threshold: float = 1.0,
    buffer_lines: int = 40,
    backup: bool = False,
    encoding: str = 'utf-8',
) -> Dict[str, Any]:
    """
    Apply a SEARCH/REPLACE diff to a file.
    
    This tool applies precise, targeted modifications to an existing file
    by searching for specific sections of content and replacing them.
    
    Diff Format:
        <<<<<<< SEARCH
        :start_line:N
        -------
        [exact content to find]
        =======
        [new content to replace with]
        >>>>>>> REPLACE
    
    Args:
        path: Path to the file (absolute or relative to workspace)
        diff: The SEARCH/REPLACE diff content
        workspace: Workspace root directory (for relative paths)
        fuzzy_threshold: Similarity threshold (0.0-1.0, 1.0 = exact match)
        buffer_lines: Lines to search around start_line hint
        backup: Whether to create a backup before modifying
        encoding: File encoding (default: utf-8)
        
    Returns:
        Dictionary with:
        - success: bool
        - path: str
        - applied_count: int (number of blocks applied)
        - failed_blocks: list (details of failed blocks)
        - error: str (if success is False)
        
    Example:
        >>> diff = '''
        ... <<<<<<< SEARCH
        ... :start_line:1
        ... -------
        ... def old_function():
        ...     pass
        ... =======
        ... def new_function():
        ...     return True
        ... >>>>>>> REPLACE
        ... '''
        >>> result = apply_diff("src/main.py", diff)
    """
    # Resolve path
    if workspace and not os.path.isabs(path):
        abs_path = os.path.abspath(os.path.join(workspace, path))
    else:
        abs_path = os.path.abspath(path)
    
    # Security check
    if workspace:
        if not is_path_within_directory(abs_path, workspace):
            return {
                'success': False,
                'error': f"Path '{path}' is outside the workspace",
                'path': path,
                'applied_count': 0,
            }
    
    # Check if file exists
    if not file_exists(abs_path):
        return {
            'success': False,
            'error': f"File not found: {path}",
            'path': path,
            'applied_count': 0,
        }
    
    try:
        # Read original content
        with open(abs_path, 'r', encoding=encoding, errors='replace') as f:
            original_content = f.read()
        
        # Apply the diff
        result = apply_search_replace_diff(
            original_content=original_content,
            diff_content=diff,
            fuzzy_threshold=fuzzy_threshold,
            buffer_lines=buffer_lines,
        )
        
        if not result.success:
            return {
                'success': False,
                'error': result.error or "Failed to apply diff",
                'path': path,
                'applied_count': result.applied_count,
                'failed_blocks': result.failed_blocks,
            }
        
        # Create backup if requested
        backup_path = None
        if backup:
            import time
            timestamp = int(time.time())
            backup_path = f"{abs_path}.backup.{timestamp}"
            with open(backup_path, 'w', encoding=encoding) as f:
                f.write(original_content)
        
        # Write the modified content
        with open(abs_path, 'w', encoding=encoding) as f:
            f.write(result.content)
        
        return {
            'success': True,
            'path': path,
            'absolute_path': abs_path,
            'applied_count': result.applied_count,
            'failed_blocks': result.failed_blocks if result.failed_blocks else None,
            'backup_path': backup_path,
        }
        
    except PermissionError:
        return {
            'success': False,
            'error': f"Permission denied: {path}",
            'path': path,
            'applied_count': 0,
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error applying diff to {path}: {str(e)}",
            'path': path,
            'applied_count': 0,
        }


def create_diff_block(
    search_content: str,
    replace_content: str,
    start_line: Optional[int] = None,
) -> str:
    """
    Create a properly formatted SEARCH/REPLACE diff block.
    
    Args:
        search_content: The content to search for
        replace_content: The content to replace with
        start_line: Optional line number hint
        
    Returns:
        Formatted diff block string
        
    Example:
        >>> diff = create_diff_block(
        ...     "def old():\\n    pass",
        ...     "def new():\\n    return True",
        ...     start_line=10
        ... )
    """
    lines = ["<<<<<<< SEARCH"]
    
    if start_line:
        lines.append(f":start_line:{start_line}")
    
    lines.append("-------")
    lines.append(search_content)
    lines.append("=======")
    lines.append(replace_content)
    lines.append(">>>>>>> REPLACE")
    
    return '\n'.join(lines)


def create_multi_diff(blocks: list) -> str:
    """
    Create a diff with multiple SEARCH/REPLACE blocks.
    
    Args:
        blocks: List of dicts with 'search', 'replace', and optional 'start_line'
        
    Returns:
        Combined diff string with all blocks
        
    Example:
        >>> diff = create_multi_diff([
        ...     {'search': 'old1', 'replace': 'new1', 'start_line': 5},
        ...     {'search': 'old2', 'replace': 'new2', 'start_line': 20},
        ... ])
    """
    diff_blocks = []
    
    for block in blocks:
        diff_block = create_diff_block(
            search_content=block.get('search', ''),
            replace_content=block.get('replace', ''),
            start_line=block.get('start_line'),
        )
        diff_blocks.append(diff_block)
    
    return '\n\n'.join(diff_blocks)
