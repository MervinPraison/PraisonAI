"""
List Files Tool for PraisonAI Code.

Provides functionality to list directory contents with filtering options.
"""

import os
from typing import Optional, List, Dict, Any

from ..utils.ignore_utils import (
    should_ignore_path,
    load_gitignore_patterns,
)


def list_files(
    path: str,
    recursive: bool = False,
    workspace: Optional[str] = None,
    max_files: int = 200,
    include_hidden: bool = False,
    extensions: Optional[List[str]] = None,
    respect_gitignore: bool = True,
) -> Dict[str, Any]:
    """
    List files and directories in a given path.
    
    This tool lists the contents of a directory, optionally recursively,
    with support for filtering and gitignore patterns.
    
    Args:
        path: Path to the directory (absolute or relative to workspace)
        recursive: Whether to list recursively
        workspace: Workspace root directory (for relative paths)
        max_files: Maximum number of files to return
        include_hidden: Whether to include hidden files (starting with .)
        extensions: List of file extensions to include (e.g., ['py', 'js'])
        respect_gitignore: Whether to respect .gitignore patterns
        
    Returns:
        Dictionary with:
        - success: bool
        - files: List of file entries with path, type, size
        - directories: List of directory entries
        - total_count: int (total items found)
        - truncated: bool (True if max_files was reached)
        - error: str (if success is False)
        
    Example:
        >>> result = list_files("src", recursive=True, extensions=['py'])
        >>> for f in result['files']:
        ...     print(f['path'])
    """
    # Resolve path
    if workspace and not os.path.isabs(path):
        abs_path = os.path.abspath(os.path.join(workspace, path))
    else:
        abs_path = os.path.abspath(path)
    
    # Check if directory exists
    if not os.path.isdir(abs_path):
        return {
            'success': False,
            'error': f"Directory not found: {path}",
            'files': [],
            'directories': [],
            'total_count': 0,
        }
    
    # Load gitignore patterns
    ignore_patterns = []
    if respect_gitignore:
        # Load from workspace root if available
        if workspace:
            ignore_patterns = load_gitignore_patterns(workspace)
        # Also load from the target directory
        ignore_patterns.extend(load_gitignore_patterns(abs_path))
    
    files = []
    directories = []
    total_count = 0
    truncated = False
    
    try:
        if recursive:
            # Walk directory tree
            for root, dirs, filenames in os.walk(abs_path):
                # Filter hidden directories
                if not include_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                
                # Filter ignored directories
                if respect_gitignore:
                    base_dir = workspace or abs_path
                    dirs[:] = [
                        d for d in dirs 
                        if not should_ignore_path(
                            os.path.join(root, d), 
                            ignore_patterns, 
                            base_dir, 
                            is_directory=True
                        )
                    ]
                
                # Process files
                for filename in filenames:
                    if total_count >= max_files:
                        truncated = True
                        break
                    
                    # Skip hidden files
                    if not include_hidden and filename.startswith('.'):
                        continue
                    
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, abs_path)
                    
                    # Check gitignore
                    if respect_gitignore:
                        base_dir = workspace or abs_path
                        if should_ignore_path(file_path, ignore_patterns, base_dir):
                            continue
                    
                    # Filter by extension
                    if extensions:
                        ext = os.path.splitext(filename)[1].lstrip('.')
                        if ext.lower() not in [e.lower() for e in extensions]:
                            continue
                    
                    # Get file info
                    try:
                        stat = os.stat(file_path)
                        files.append({
                            'path': rel_path,
                            'name': filename,
                            'size': stat.st_size,
                            'modified': stat.st_mtime,
                        })
                        total_count += 1
                    except OSError:
                        continue
                
                if truncated:
                    break
                
                # Add directories
                for dirname in dirs:
                    if total_count >= max_files:
                        truncated = True
                        break
                    
                    dir_path = os.path.join(root, dirname)
                    rel_path = os.path.relpath(dir_path, abs_path)
                    
                    directories.append({
                        'path': rel_path,
                        'name': dirname,
                    })
                    total_count += 1
        else:
            # List only top level
            for entry in os.listdir(abs_path):
                if total_count >= max_files:
                    truncated = True
                    break
                
                # Skip hidden files
                if not include_hidden and entry.startswith('.'):
                    continue
                
                entry_path = os.path.join(abs_path, entry)
                
                # Check gitignore
                if respect_gitignore:
                    base_dir = workspace or abs_path
                    is_dir = os.path.isdir(entry_path)
                    if should_ignore_path(entry_path, ignore_patterns, base_dir, is_dir):
                        continue
                
                if os.path.isfile(entry_path):
                    # Filter by extension
                    if extensions:
                        ext = os.path.splitext(entry)[1].lstrip('.')
                        if ext.lower() not in [e.lower() for e in extensions]:
                            continue
                    
                    try:
                        stat = os.stat(entry_path)
                        files.append({
                            'path': entry,
                            'name': entry,
                            'size': stat.st_size,
                            'modified': stat.st_mtime,
                        })
                        total_count += 1
                    except OSError:
                        continue
                        
                elif os.path.isdir(entry_path):
                    directories.append({
                        'path': entry,
                        'name': entry,
                    })
                    total_count += 1
        
        # Sort results
        files.sort(key=lambda x: x['path'])
        directories.sort(key=lambda x: x['path'])
        
        return {
            'success': True,
            'files': files,
            'directories': directories,
            'total_count': total_count,
            'truncated': truncated,
            'path': path,
        }
        
    except PermissionError:
        return {
            'success': False,
            'error': f"Permission denied: {path}",
            'files': [],
            'directories': [],
            'total_count': 0,
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error listing {path}: {str(e)}",
            'files': [],
            'directories': [],
            'total_count': 0,
        }


def format_file_list(result: Dict[str, Any], show_size: bool = True) -> str:
    """
    Format a list_files result as a readable string.
    
    Args:
        result: Result from list_files()
        show_size: Whether to show file sizes
        
    Returns:
        Formatted string representation
    """
    if not result['success']:
        return f"Error: {result.get('error', 'Unknown error')}"
    
    lines = []
    
    # Add directories first
    for d in result['directories']:
        lines.append(f"📁 {d['path']}/")
    
    # Add files
    for f in result['files']:
        if show_size:
            size = f.get('size', 0)
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f}KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f}MB"
            lines.append(f"📄 {f['path']} ({size_str})")
        else:
            lines.append(f"📄 {f['path']}")
    
    if result.get('truncated'):
        lines.append(f"\n... (truncated, showing {result['total_count']} of more items)")
    
    return '\n'.join(lines)
