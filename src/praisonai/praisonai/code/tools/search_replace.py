"""
Search and Replace Tool for PraisonAI Code.

Provides functionality to perform multiple search/replace operations
on a file in a single operation.
"""

import os
import re
from typing import Optional, List, Dict, Any

from ..utils.file_utils import (
    file_exists,
    is_path_within_directory,
)


def search_replace(
    path: str,
    operations: List[Dict[str, Any]],
    workspace: Optional[str] = None,
    backup: bool = False,
    encoding: str = 'utf-8',
) -> Dict[str, Any]:
    """
    Perform multiple search/replace operations on a file.
    
    This tool allows precise modifications to file content by performing
    multiple search and replace operations in sequence.
    
    Args:
        path: Path to the file (absolute or relative to workspace)
        operations: List of operations, each with:
            - search: str (text to find)
            - replace: str (text to replace with)
            - is_regex: bool (optional, treat search as regex)
            - count: int (optional, max replacements, -1 for all)
        workspace: Workspace root directory
        backup: Whether to create a backup before modifying
        encoding: File encoding
        
    Returns:
        Dictionary with:
        - success: bool
        - path: str
        - operations_applied: int
        - total_replacements: int
        - failed_operations: list
        - error: str (if success is False)
        
    Example:
        >>> operations = [
        ...     {'search': 'old_name', 'replace': 'new_name'},
        ...     {'search': r'def (\\w+)\\(', 'replace': r'def renamed_\\\\1(', 'is_regex': True},
        ... ]
        >>> result = search_replace("src/main.py", operations)
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
                'operations_applied': 0,
                'total_replacements': 0,
            }
    
    # Check if file exists
    if not file_exists(abs_path):
        return {
            'success': False,
            'error': f"File not found: {path}",
            'path': path,
            'operations_applied': 0,
            'total_replacements': 0,
        }
    
    if not operations:
        return {
            'success': False,
            'error': "No operations provided",
            'path': path,
            'operations_applied': 0,
            'total_replacements': 0,
        }
    
    try:
        # Read original content
        with open(abs_path, 'r', encoding=encoding, errors='replace') as f:
            content = f.read()
        
        original_content = content
        operations_applied = 0
        total_replacements = 0
        failed_operations = []
        
        # Apply each operation
        for i, op in enumerate(operations):
            search = op.get('search')
            replace = op.get('replace', '')
            is_regex = op.get('is_regex', False)
            count = op.get('count', -1)  # -1 means replace all
            
            if not search:
                failed_operations.append({
                    'index': i,
                    'error': "Missing 'search' field",
                })
                continue
            
            try:
                if is_regex:
                    # Regex replacement
                    if count == -1:
                        new_content, num_subs = re.subn(search, replace, content)
                    else:
                        new_content, num_subs = re.subn(search, replace, content, count=count)
                else:
                    # Literal replacement
                    if count == -1:
                        num_subs = content.count(search)
                        new_content = content.replace(search, replace)
                    else:
                        num_subs = min(content.count(search), count)
                        new_content = content
                        for _ in range(count):
                            if search in new_content:
                                new_content = new_content.replace(search, replace, 1)
                            else:
                                break
                
                if num_subs > 0:
                    content = new_content
                    operations_applied += 1
                    total_replacements += num_subs
                else:
                    failed_operations.append({
                        'index': i,
                        'search': search[:50],
                        'error': "No matches found",
                    })
                    
            except re.error as e:
                failed_operations.append({
                    'index': i,
                    'search': search[:50],
                    'error': f"Invalid regex: {str(e)}",
                })
        
        # Check if any changes were made
        if content == original_content:
            return {
                'success': False,
                'error': "No changes were made - no matches found",
                'path': path,
                'operations_applied': 0,
                'total_replacements': 0,
                'failed_operations': failed_operations,
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
            f.write(content)
        
        return {
            'success': True,
            'path': path,
            'absolute_path': abs_path,
            'operations_applied': operations_applied,
            'total_replacements': total_replacements,
            'failed_operations': failed_operations if failed_operations else None,
            'backup_path': backup_path,
        }
        
    except PermissionError:
        return {
            'success': False,
            'error': f"Permission denied: {path}",
            'path': path,
            'operations_applied': 0,
            'total_replacements': 0,
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error performing search/replace on {path}: {str(e)}",
            'path': path,
            'operations_applied': 0,
            'total_replacements': 0,
        }


def simple_replace(
    path: str,
    search: str,
    replace: str,
    workspace: Optional[str] = None,
    is_regex: bool = False,
    count: int = -1,
    backup: bool = False,
    encoding: str = 'utf-8',
) -> Dict[str, Any]:
    """
    Perform a single search/replace operation on a file.
    
    Convenience wrapper around search_replace for single operations.
    
    Args:
        path: Path to the file
        search: Text to find
        replace: Text to replace with
        workspace: Workspace root directory
        is_regex: Whether search is a regex pattern
        count: Max replacements (-1 for all)
        backup: Whether to create a backup
        encoding: File encoding
        
    Returns:
        Dictionary with success status and details
    """
    return search_replace(
        path=path,
        operations=[{
            'search': search,
            'replace': replace,
            'is_regex': is_regex,
            'count': count,
        }],
        workspace=workspace,
        backup=backup,
        encoding=encoding,
    )
