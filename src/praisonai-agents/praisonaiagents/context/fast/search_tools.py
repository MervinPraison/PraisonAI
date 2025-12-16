"""
Search tools for Fast Context.

Provides cross-platform compatible search tools:
- grep_search: Pattern search in files
- glob_search: File pattern matching
- read_file: Read file contents with line range support
- list_directory: List directory contents

These tools are designed to be fast, safe, and cross-platform compatible.
"""

import os
import re
import fnmatch
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
import logging

logger = logging.getLogger(__name__)


def _load_gitignore_patterns(root_path: str) -> Set[str]:
    """Load patterns from .gitignore file.
    
    Args:
        root_path: Root directory to search for .gitignore
        
    Returns:
        Set of gitignore patterns
    """
    patterns = set()
    gitignore_path = Path(root_path) / ".gitignore"
    
    if gitignore_path.exists():
        try:
            with open(gitignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        patterns.add(line)
        except Exception:
            pass
    
    # Also check for .praisonignore
    praisonignore_path = Path(root_path) / ".praisonignore"
    if praisonignore_path.exists():
        try:
            with open(praisonignore_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        patterns.add(line)
        except Exception:
            pass
    
    return patterns


def _should_ignore(path: str, root_path: str, patterns: Set[str]) -> bool:
    """Check if a path should be ignored based on gitignore patterns.
    
    Args:
        path: Path to check
        root_path: Root directory
        patterns: Set of gitignore patterns
        
    Returns:
        True if path should be ignored
    """
    if not patterns:
        return False
    
    rel_path = os.path.relpath(path, root_path)
    path_parts = Path(rel_path).parts
    
    for pattern in patterns:
        # Handle directory patterns (ending with /)
        if pattern.endswith('/'):
            dir_pattern = pattern.rstrip('/')
            if any(fnmatch.fnmatch(part, dir_pattern) for part in path_parts):
                return True
        # Handle ** patterns
        elif '**' in pattern:
            # Convert gitignore pattern to fnmatch pattern
            fnmatch_pattern = pattern.replace('**/', '*').replace('**', '*')
            if fnmatch.fnmatch(rel_path, fnmatch_pattern):
                return True
        # Handle simple patterns
        else:
            # Check against filename
            if fnmatch.fnmatch(os.path.basename(path), pattern):
                return True
            # Check against relative path
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Check if any path component matches
            if any(fnmatch.fnmatch(part, pattern) for part in path_parts):
                return True
    
    return False


def _is_binary_file(filepath: str) -> bool:
    """Check if a file is binary.
    
    Args:
        filepath: Path to the file
        
    Returns:
        True if file appears to be binary
    """
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(8192)
            # Check for null bytes (common in binary files)
            if b'\x00' in chunk:
                return True
            # Check for high ratio of non-text characters
            text_chars = bytearray({7, 8, 9, 10, 12, 13, 27} | set(range(0x20, 0x100)) - {0x7f})
            non_text = sum(1 for byte in chunk if byte not in text_chars)
            if len(chunk) > 0 and non_text / len(chunk) > 0.3:
                return True
    except Exception:
        return True
    return False


def grep_search(
    search_path: str,
    pattern: str,
    is_regex: bool = False,
    case_sensitive: bool = False,
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    max_results: int = 100,
    context_lines: int = 0,
    respect_gitignore: bool = True
) -> List[Dict[str, Any]]:
    """Search for pattern in files.
    
    Args:
        search_path: Directory or file to search
        pattern: Search pattern (string or regex)
        is_regex: If True, treat pattern as regex
        case_sensitive: If True, search is case sensitive
        include_patterns: Glob patterns to include (e.g., ["*.py"])
        exclude_patterns: Glob patterns to exclude (e.g., ["**/test_*"])
        max_results: Maximum number of results to return
        context_lines: Number of context lines before/after match
        respect_gitignore: If True, respect .gitignore patterns
        
    Returns:
        List of match dictionaries with path, line_number, content, context
    """
    results = []
    search_path = os.path.abspath(search_path)
    
    # Compile pattern
    if is_regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            logger.warning(f"Invalid regex pattern: {e}")
            return []
    else:
        if case_sensitive:
            regex = re.compile(re.escape(pattern))
        else:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)
    
    # Load gitignore patterns
    gitignore_patterns = set()
    if respect_gitignore:
        gitignore_patterns = _load_gitignore_patterns(search_path)
    
    # Get files to search
    if os.path.isfile(search_path):
        files_to_search = [search_path]
    else:
        files_to_search = []
        for root, dirs, files in os.walk(search_path):
            # Filter directories in-place to skip ignored ones
            if respect_gitignore:
                dirs[:] = [d for d in dirs if not _should_ignore(
                    os.path.join(root, d), search_path, gitignore_patterns
                )]
            
            for filename in files:
                filepath = os.path.join(root, filename)
                
                # Check gitignore
                if respect_gitignore and _should_ignore(filepath, search_path, gitignore_patterns):
                    continue
                
                # Check include patterns
                if include_patterns:
                    rel_path = os.path.relpath(filepath, search_path)
                    if not any(fnmatch.fnmatch(rel_path, p) or fnmatch.fnmatch(filename, p) 
                              for p in include_patterns):
                        continue
                
                # Check exclude patterns
                if exclude_patterns:
                    rel_path = os.path.relpath(filepath, search_path)
                    if any(fnmatch.fnmatch(rel_path, p) or fnmatch.fnmatch(filename, p) 
                          for p in exclude_patterns):
                        continue
                
                files_to_search.append(filepath)
    
    # Search files
    for filepath in files_to_search:
        if len(results) >= max_results:
            break
        
        # Skip binary files
        if _is_binary_file(filepath):
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            for i, line in enumerate(lines):
                if len(results) >= max_results:
                    break
                
                if regex.search(line):
                    # Get context
                    start_ctx = max(0, i - context_lines)
                    end_ctx = min(len(lines), i + context_lines + 1)
                    context = ''.join(lines[start_ctx:end_ctx])
                    
                    results.append({
                        "path": os.path.relpath(filepath, search_path),
                        "absolute_path": filepath,
                        "line_number": i + 1,  # 1-indexed
                        "content": line.rstrip('\n\r'),
                        "context": context.rstrip('\n\r') if context_lines > 0 else None,
                        "context_start": start_ctx + 1 if context_lines > 0 else None,
                        "context_end": end_ctx if context_lines > 0 else None
                    })
        except Exception as e:
            logger.debug(f"Error reading {filepath}: {e}")
            continue
    
    return results


def glob_search(
    search_path: str,
    pattern: str,
    max_results: int = 100,
    include_dirs: bool = False,
    respect_gitignore: bool = True
) -> List[Dict[str, Any]]:
    """Search for files matching glob pattern.
    
    Args:
        search_path: Directory to search
        pattern: Glob pattern (e.g., "**/*.py", "src/*.js")
        max_results: Maximum number of results
        include_dirs: If True, include directories in results
        respect_gitignore: If True, respect .gitignore patterns
        
    Returns:
        List of file info dictionaries with path, size, is_dir
    """
    results = []
    search_path = os.path.abspath(search_path)
    
    # Load gitignore patterns
    gitignore_patterns = set()
    if respect_gitignore:
        gitignore_patterns = _load_gitignore_patterns(search_path)
    
    # Use pathlib for glob
    root = Path(search_path)
    
    try:
        for match in root.glob(pattern):
            if len(results) >= max_results:
                break
            
            # Check gitignore
            if respect_gitignore and _should_ignore(str(match), search_path, gitignore_patterns):
                continue
            
            # Skip directories unless requested
            if match.is_dir() and not include_dirs:
                continue
            
            # Skip binary files for file results
            if match.is_file() and _is_binary_file(str(match)):
                continue
            
            try:
                stat = match.stat()
                results.append({
                    "path": str(match.relative_to(root)),
                    "absolute_path": str(match),
                    "size": stat.st_size if match.is_file() else None,
                    "is_dir": match.is_dir(),
                    "modified": stat.st_mtime
                })
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Error in glob search: {e}")
    
    return results


def read_file(
    filepath: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    context_lines: int = 0,
    max_lines: int = 500
) -> Dict[str, Any]:
    """Read file contents with optional line range.
    
    Args:
        filepath: Path to the file
        start_line: Starting line (1-indexed, inclusive)
        end_line: Ending line (1-indexed, inclusive)
        context_lines: Additional context lines before/after range
        max_lines: Maximum lines to return
        
    Returns:
        Dictionary with content, line info, and metadata
    """
    filepath = os.path.abspath(filepath)
    
    if not os.path.exists(filepath):
        return {
            "success": False,
            "error": f"File not found: {filepath}",
            "path": filepath
        }
    
    if os.path.isdir(filepath):
        return {
            "success": False,
            "error": f"Path is a directory: {filepath}",
            "path": filepath
        }
    
    if _is_binary_file(filepath):
        return {
            "success": False,
            "error": f"Binary file: {filepath}",
            "path": filepath
        }
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        
        # Determine line range
        if start_line is None:
            start_line = 1
        if end_line is None:
            end_line = total_lines
        
        # Apply context
        actual_start = max(1, start_line - context_lines)
        actual_end = min(total_lines, end_line + context_lines)
        
        # Limit lines
        if actual_end - actual_start + 1 > max_lines:
            actual_end = actual_start + max_lines - 1
        
        # Extract content (convert to 0-indexed)
        content_lines = lines[actual_start - 1:actual_end]
        content = ''.join(content_lines)
        
        return {
            "success": True,
            "path": filepath,
            "content": content.rstrip('\n'),
            "start_line": actual_start,
            "end_line": actual_end,
            "total_lines": total_lines,
            "lines_returned": len(content_lines)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "path": filepath
        }


def list_directory(
    dir_path: str,
    recursive: bool = False,
    max_depth: int = 10,
    max_entries: int = 500,
    include_hidden: bool = False,
    respect_gitignore: bool = True
) -> Dict[str, Any]:
    """List directory contents.
    
    Args:
        dir_path: Directory path
        recursive: If True, list recursively
        max_depth: Maximum recursion depth
        max_entries: Maximum entries to return
        include_hidden: If True, include hidden files/dirs
        respect_gitignore: If True, respect .gitignore patterns
        
    Returns:
        Dictionary with entries list and metadata
    """
    dir_path = os.path.abspath(dir_path)
    
    if not os.path.exists(dir_path):
        return {
            "success": False,
            "error": f"Directory not found: {dir_path}",
            "path": dir_path
        }
    
    if not os.path.isdir(dir_path):
        return {
            "success": False,
            "error": f"Not a directory: {dir_path}",
            "path": dir_path
        }
    
    # Load gitignore patterns
    gitignore_patterns = set()
    if respect_gitignore:
        gitignore_patterns = _load_gitignore_patterns(dir_path)
    
    entries = []
    
    def _list_dir(path: str, depth: int):
        if depth > max_depth or len(entries) >= max_entries:
            return
        
        try:
            for entry in os.scandir(path):
                if len(entries) >= max_entries:
                    break
                
                # Skip hidden files unless requested
                if not include_hidden and entry.name.startswith('.'):
                    continue
                
                # Check gitignore
                if respect_gitignore and _should_ignore(entry.path, dir_path, gitignore_patterns):
                    continue
                
                try:
                    stat = entry.stat()
                    entries.append({
                        "name": entry.name,
                        "path": os.path.relpath(entry.path, dir_path),
                        "absolute_path": entry.path,
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size if entry.is_file() else None,
                        "modified": stat.st_mtime
                    })
                except Exception:
                    continue
                
                # Recurse into directories
                if recursive and entry.is_dir():
                    _list_dir(entry.path, depth + 1)
        except PermissionError:
            pass
        except Exception as e:
            logger.debug(f"Error listing {path}: {e}")
    
    _list_dir(dir_path, 0)
    
    # Sort entries: directories first, then by name
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    
    return {
        "success": True,
        "path": dir_path,
        "entries": entries,
        "total_entries": len(entries),
        "truncated": len(entries) >= max_entries
    }


# Tool definitions for LLM function calling
FAST_CONTEXT_TOOLS = [
    {
        "name": "grep_search",
        "description": "Search for a pattern in files within a directory. Returns matching lines with file paths and line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "search_path": {
                    "type": "string",
                    "description": "Directory or file path to search"
                },
                "pattern": {
                    "type": "string",
                    "description": "Search pattern (text or regex)"
                },
                "is_regex": {
                    "type": "boolean",
                    "description": "If true, treat pattern as regex",
                    "default": False
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "If true, search is case sensitive",
                    "default": False
                },
                "include_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns to include (e.g., ['*.py'])"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 50
                }
            },
            "required": ["search_path", "pattern"]
        }
    },
    {
        "name": "glob_search",
        "description": "Find files matching a glob pattern. Returns file paths and metadata.",
        "parameters": {
            "type": "object",
            "properties": {
                "search_path": {
                    "type": "string",
                    "description": "Directory to search"
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', 'src/*.js')"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 50
                }
            },
            "required": ["search_path", "pattern"]
        }
    },
    {
        "name": "read_file",
        "description": "Read contents of a file, optionally with specific line range.",
        "parameters": {
            "type": "object",
            "properties": {
                "filepath": {
                    "type": "string",
                    "description": "Path to the file"
                },
                "start_line": {
                    "type": "integer",
                    "description": "Starting line number (1-indexed)"
                },
                "end_line": {
                    "type": "integer",
                    "description": "Ending line number (1-indexed)"
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Additional context lines",
                    "default": 0
                }
            },
            "required": ["filepath"]
        }
    },
    {
        "name": "list_directory",
        "description": "List contents of a directory.",
        "parameters": {
            "type": "object",
            "properties": {
                "dir_path": {
                    "type": "string",
                    "description": "Directory path"
                },
                "recursive": {
                    "type": "boolean",
                    "description": "If true, list recursively",
                    "default": False
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum recursion depth",
                    "default": 3
                }
            },
            "required": ["dir_path"]
        }
    }
]


def execute_tool(tool_name: str, **kwargs) -> Dict[str, Any]:
    """Execute a search tool by name.
    
    Args:
        tool_name: Name of the tool to execute
        **kwargs: Tool arguments
        
    Returns:
        Tool result dictionary
    """
    tools = {
        "grep_search": grep_search,
        "glob_search": glob_search,
        "read_file": read_file,
        "list_directory": list_directory
    }
    
    if tool_name not in tools:
        return {"error": f"Unknown tool: {tool_name}"}
    
    try:
        return tools[tool_name](**kwargs)
    except Exception as e:
        return {"error": str(e)}
