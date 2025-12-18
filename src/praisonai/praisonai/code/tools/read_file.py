"""
Read File Tool for PraisonAI Code.

Provides functionality to read file contents with optional line ranges
and line number annotations.
"""

import os
from typing import Optional, List, Dict, Any

from ..utils.file_utils import (
    add_line_numbers,
    is_binary_file,
    file_exists,
    is_path_within_directory,
)


def read_file(
    path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    add_line_nums: bool = True,
    workspace: Optional[str] = None,
    encoding: str = 'utf-8',
) -> Dict[str, Any]:
    """
    Read file contents with optional line range and line numbers.
    
    This tool reads the contents of a file, optionally limiting to specific
    line ranges and adding line number annotations for AI context.
    
    Args:
        path: Path to the file (absolute or relative to workspace)
        start_line: First line to read (1-indexed, inclusive)
        end_line: Last line to read (1-indexed, inclusive)
        add_line_nums: Whether to add line numbers to output
        workspace: Workspace root directory (for relative paths)
        encoding: File encoding (default: utf-8)
        
    Returns:
        Dictionary with:
        - success: bool
        - content: str (file content, possibly with line numbers)
        - total_lines: int (total lines in file)
        - start_line: int (actual start line read)
        - end_line: int (actual end line read)
        - error: str (if success is False)
        
    Example:
        >>> result = read_file("src/main.py", start_line=1, end_line=50)
        >>> if result['success']:
        ...     print(result['content'])
    """
    # Resolve path
    if workspace and not os.path.isabs(path):
        abs_path = os.path.abspath(os.path.join(workspace, path))
    else:
        abs_path = os.path.abspath(path)
    
    # Security check - ensure path is within workspace if specified
    if workspace:
        if not is_path_within_directory(abs_path, workspace):
            return {
                'success': False,
                'error': f"Path '{path}' is outside the workspace",
                'content': None,
                'total_lines': 0,
            }
    
    # Check if file exists
    if not file_exists(abs_path):
        return {
            'success': False,
            'error': f"File not found: {path}",
            'content': None,
            'total_lines': 0,
        }
    
    # Check if binary
    if is_binary_file(abs_path):
        return {
            'success': False,
            'error': f"Cannot read binary file: {path}",
            'content': None,
            'total_lines': 0,
        }
    
    try:
        # Read file content
        with open(abs_path, 'r', encoding=encoding, errors='replace') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        # Determine line range
        actual_start = start_line if start_line and start_line > 0 else 1
        actual_end = end_line if end_line and end_line > 0 else total_lines
        
        # Clamp to valid range
        actual_start = max(1, min(actual_start, total_lines))
        actual_end = max(actual_start, min(actual_end, total_lines))
        
        # Extract lines (convert to 0-indexed)
        selected_lines = lines[actual_start - 1:actual_end]
        content = ''.join(selected_lines)
        
        # Remove trailing newline if present
        if content.endswith('\n'):
            content = content[:-1]
        
        # Add line numbers if requested
        if add_line_nums:
            content = add_line_numbers(content, actual_start)
        
        return {
            'success': True,
            'content': content,
            'total_lines': total_lines,
            'start_line': actual_start,
            'end_line': actual_end,
            'path': path,
        }
        
    except PermissionError:
        return {
            'success': False,
            'error': f"Permission denied: {path}",
            'content': None,
            'total_lines': 0,
        }
    except UnicodeDecodeError as e:
        return {
            'success': False,
            'error': f"Encoding error reading {path}: {e}",
            'content': None,
            'total_lines': 0,
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error reading {path}: {str(e)}",
            'content': None,
            'total_lines': 0,
        }


def read_multiple_files(
    files: List[Dict[str, Any]],
    workspace: Optional[str] = None,
    add_line_nums: bool = True,
) -> Dict[str, Any]:
    """
    Read multiple files in a single operation.
    
    Args:
        files: List of file specifications, each with:
            - path: str (required)
            - start_line: int (optional)
            - end_line: int (optional)
        workspace: Workspace root directory
        add_line_nums: Whether to add line numbers
        
    Returns:
        Dictionary with:
        - success: bool (True if all files read successfully)
        - results: List of individual file results
        - errors: List of error messages
        
    Example:
        >>> files = [
        ...     {'path': 'src/main.py', 'start_line': 1, 'end_line': 50},
        ...     {'path': 'src/utils.py'},
        ... ]
        >>> result = read_multiple_files(files, workspace='/project')
    """
    results = []
    errors = []
    all_success = True
    
    for file_spec in files:
        path = file_spec.get('path')
        if not path:
            errors.append("Missing 'path' in file specification")
            all_success = False
            continue
        
        result = read_file(
            path=path,
            start_line=file_spec.get('start_line'),
            end_line=file_spec.get('end_line'),
            add_line_nums=add_line_nums,
            workspace=workspace,
        )
        
        results.append(result)
        
        if not result['success']:
            all_success = False
            errors.append(result.get('error', f"Failed to read {path}"))
    
    return {
        'success': all_success,
        'results': results,
        'errors': errors if errors else None,
    }
