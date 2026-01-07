"""
Glob tool for finding files matching patterns.

Provides a simple interface for file discovery with glob patterns.
"""

import fnmatch
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


def glob_files(
    pattern: str,
    directory: Optional[str] = None,
    recursive: bool = True,
    exclude: Optional[List[str]] = None,
    max_results: int = 1000,
    include_hidden: bool = False,
) -> Dict[str, Any]:
    """
    Find files matching a glob pattern.
    
    Args:
        pattern: Glob pattern to match (e.g., "*.py", "**/*.js")
        directory: Directory to search in (default: current directory)
        recursive: Whether to search recursively (default: True)
        exclude: List of patterns to exclude
        max_results: Maximum number of results to return
        include_hidden: Whether to include hidden files/directories
    
    Returns:
        Dict with:
            - success: Whether the search completed
            - files: List of matching file paths (absolute)
            - count: Number of matches
            - truncated: Whether results were truncated
            - error: Error message if any
    
    Example:
        >>> glob_files("*.py", directory="/project/src")
        {'success': True, 'files': ['/project/src/main.py', ...], 'count': 5, ...}
    """
    result = {
        "success": False,
        "files": [],
        "count": 0,
        "truncated": False,
        "error": None,
    }
    
    try:
        # Default to current directory
        if directory is None:
            directory = os.getcwd()
        
        directory = os.path.abspath(directory)
        
        if not os.path.isdir(directory):
            result["error"] = f"Directory not found: {directory}"
            return result
        
        exclude = exclude or []
        matches = []
        
        # Use pathlib for glob
        base_path = Path(directory)
        
        # Handle recursive pattern
        if recursive and "**" not in pattern:
            # Make pattern recursive if not already
            search_pattern = f"**/{pattern}"
        else:
            search_pattern = pattern
        
        for path in base_path.glob(search_pattern):
            # Skip directories
            if path.is_dir():
                continue
            
            # Skip hidden files/directories if not included
            if not include_hidden:
                parts = path.relative_to(base_path).parts
                if any(part.startswith('.') for part in parts):
                    continue
            
            # Check exclusions
            rel_path = str(path.relative_to(base_path))
            excluded = False
            for exc_pattern in exclude:
                if fnmatch.fnmatch(rel_path, exc_pattern):
                    excluded = True
                    break
                if fnmatch.fnmatch(path.name, exc_pattern):
                    excluded = True
                    break
            
            if excluded:
                continue
            
            matches.append(str(path.absolute()))
            
            if len(matches) >= max_results:
                result["truncated"] = True
                break
        
        result["files"] = matches
        result["count"] = len(matches)
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def glob_directories(
    pattern: str,
    directory: Optional[str] = None,
    recursive: bool = True,
    exclude: Optional[List[str]] = None,
    max_results: int = 1000,
) -> Dict[str, Any]:
    """
    Find directories matching a glob pattern.
    
    Args:
        pattern: Glob pattern to match
        directory: Directory to search in (default: current directory)
        recursive: Whether to search recursively
        exclude: List of patterns to exclude
        max_results: Maximum number of results
    
    Returns:
        Dict with directories list and metadata.
    """
    result = {
        "success": False,
        "directories": [],
        "count": 0,
        "truncated": False,
        "error": None,
    }
    
    try:
        if directory is None:
            directory = os.getcwd()
        
        directory = os.path.abspath(directory)
        
        if not os.path.isdir(directory):
            result["error"] = f"Directory not found: {directory}"
            return result
        
        exclude = exclude or []
        matches = []
        
        base_path = Path(directory)
        
        if recursive and "**" not in pattern:
            search_pattern = f"**/{pattern}"
        else:
            search_pattern = pattern
        
        for path in base_path.glob(search_pattern):
            if not path.is_dir():
                continue
            
            rel_path = str(path.relative_to(base_path))
            excluded = False
            for exc_pattern in exclude:
                if fnmatch.fnmatch(rel_path, exc_pattern):
                    excluded = True
                    break
            
            if excluded:
                continue
            
            matches.append(str(path.absolute()))
            
            if len(matches) >= max_results:
                result["truncated"] = True
                break
        
        result["directories"] = matches
        result["count"] = len(matches)
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result
