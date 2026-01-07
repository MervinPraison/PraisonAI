"""
Grep tool for searching file contents.

Provides a simple interface for searching text patterns in files.
"""

import fnmatch
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def grep_search(
    pattern: str,
    directory: Optional[str] = None,
    include: Optional[str] = None,
    exclude: Optional[List[str]] = None,
    case_sensitive: bool = True,
    regex: bool = False,
    context: int = 0,
    max_results: int = 100,
    max_file_size: int = 1024 * 1024,  # 1MB
) -> Dict[str, Any]:
    """
    Search for a pattern in files.
    
    Args:
        pattern: Text or regex pattern to search for
        directory: Directory to search in (default: current directory)
        include: File pattern to include (e.g., "*.py")
        exclude: List of patterns to exclude
        case_sensitive: Whether search is case-sensitive
        regex: Whether pattern is a regex
        context: Number of context lines before/after match
        max_results: Maximum number of matches to return
        max_file_size: Maximum file size to search (bytes)
    
    Returns:
        Dict with:
            - success: Whether the search completed
            - matches: List of match objects with file, line_number, content
            - count: Total number of matches
            - files_searched: Number of files searched
            - truncated: Whether results were truncated
            - error: Error message if any
    
    Example:
        >>> grep_search("def hello", directory="/project", include="*.py")
        {'success': True, 'matches': [{'file': '...', 'line_number': 10, ...}], ...}
    """
    result = {
        "success": False,
        "matches": [],
        "count": 0,
        "files_searched": 0,
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
        
        # Compile pattern
        if regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                compiled_pattern = re.compile(pattern, flags)
            except re.error as e:
                result["error"] = f"Invalid regex: {e}"
                return result
        else:
            if not case_sensitive:
                pattern = pattern.lower()
            compiled_pattern = None
        
        matches = []
        files_searched = 0
        
        # Walk directory
        for root, dirs, files in os.walk(directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            # Skip excluded directories
            dirs[:] = [d for d in dirs if not any(
                fnmatch.fnmatch(d, exc) for exc in exclude
            )]
            
            for filename in files:
                # Skip hidden files
                if filename.startswith('.'):
                    continue
                
                # Check include pattern
                if include and not fnmatch.fnmatch(filename, include):
                    continue
                
                # Check exclude patterns
                if any(fnmatch.fnmatch(filename, exc) for exc in exclude):
                    continue
                
                filepath = os.path.join(root, filename)
                
                # Skip large files
                try:
                    if os.path.getsize(filepath) > max_file_size:
                        continue
                except OSError:
                    continue
                
                # Search file
                file_matches = _search_file(
                    filepath,
                    pattern,
                    compiled_pattern,
                    case_sensitive,
                    context,
                    max_results - len(matches),
                )
                
                if file_matches:
                    matches.extend(file_matches)
                    files_searched += 1
                else:
                    files_searched += 1
                
                if len(matches) >= max_results:
                    result["truncated"] = True
                    break
            
            if len(matches) >= max_results:
                break
        
        result["matches"] = matches
        result["count"] = len(matches)
        result["files_searched"] = files_searched
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result


def _search_file(
    filepath: str,
    pattern: str,
    compiled_pattern: Optional[re.Pattern],
    case_sensitive: bool,
    context: int,
    max_matches: int,
) -> List[Dict[str, Any]]:
    """Search a single file for matches."""
    matches = []
    
    try:
        with open(filepath, 'r', errors='ignore') as f:
            lines = f.readlines()
    except (IOError, OSError):
        return matches
    
    for i, line in enumerate(lines):
        line_stripped = line.rstrip('\n\r')
        
        # Check for match
        if compiled_pattern:
            match = compiled_pattern.search(line_stripped)
        else:
            search_line = line_stripped if case_sensitive else line_stripped.lower()
            match = pattern in search_line
        
        if match:
            match_info = {
                "file": filepath,
                "line_number": i + 1,
                "content": line_stripped,
            }
            
            # Add context if requested
            if context > 0:
                start = max(0, i - context)
                end = min(len(lines), i + context + 1)
                
                context_before = [
                    lines[j].rstrip('\n\r') 
                    for j in range(start, i)
                ]
                context_after = [
                    lines[j].rstrip('\n\r') 
                    for j in range(i + 1, end)
                ]
                
                match_info["context_before"] = context_before
                match_info["context_after"] = context_after
            
            matches.append(match_info)
            
            if len(matches) >= max_matches:
                break
    
    return matches


def grep_count(
    pattern: str,
    directory: Optional[str] = None,
    include: Optional[str] = None,
    case_sensitive: bool = True,
    regex: bool = False,
) -> Dict[str, Any]:
    """
    Count occurrences of a pattern in files.
    
    Returns count per file and total count.
    """
    result = {
        "success": False,
        "total": 0,
        "by_file": {},
        "error": None,
    }
    
    try:
        search_result = grep_search(
            pattern=pattern,
            directory=directory,
            include=include,
            case_sensitive=case_sensitive,
            regex=regex,
            max_results=10000,
        )
        
        if not search_result["success"]:
            result["error"] = search_result["error"]
            return result
        
        by_file = {}
        for match in search_result["matches"]:
            filepath = match["file"]
            by_file[filepath] = by_file.get(filepath, 0) + 1
        
        result["total"] = search_result["count"]
        result["by_file"] = by_file
        result["success"] = True
        
    except Exception as e:
        result["error"] = str(e)
    
    return result
