"""
Path Overlap Detection - Prevent write conflicts in parallel tool execution.

Detects when multiple tool calls would operate on overlapping file paths
and forces sequential execution to prevent corruption.
"""

import pathlib
from typing import List, Dict, Any, Set
from .call_executor import ToolCall

__all__ = ["detect_path_conflicts", "extract_paths", "has_write_conflicts"]


# Tool names that perform write operations
_WRITE_TOOLS = frozenset({
    "write_file", "skill_manage", "edit_file", "patch_file",
    "create_file", "save_file", "update_file", "delete_file",
    "file_write", "file_edit", "file_create", "file_delete",
    "mkdir", "rmdir", "move_file", "copy_file"
})

# Argument names that typically contain file paths
_PATH_ARG_NAMES = frozenset({
    "path", "file_path", "filepath", "dest", "destination", "target",
    "source", "src", "output", "output_path", "filename", "file",
    "directory", "dir", "folder"
})


def extract_paths(tool_call: ToolCall) -> List[pathlib.Path]:
    """Extract file paths from a tool call.
    
    Args:
        tool_call: Tool call to analyze
        
    Returns:
        List of resolved absolute paths found in the tool call
    """
    paths = []
    
    # Only check write tools
    if tool_call.function_name not in _WRITE_TOOLS:
        return paths
    
    args = tool_call.arguments or {}
    
    # Look for paths in common argument names
    for arg_name, arg_value in args.items():
        if arg_name in _PATH_ARG_NAMES and isinstance(arg_value, str):
            if not arg_value.strip():
                continue
            try:
                path = pathlib.Path(arg_value).resolve()
                paths.append(path)
            except (OSError, ValueError):
                # Invalid path, skip
                continue
    
    return paths


def paths_conflict(path1: pathlib.Path, path2: pathlib.Path) -> bool:
    """Check if two paths conflict (one is ancestor of the other).
    
    Args:
        path1: First path
        path2: Second path
        
    Returns:
        True if paths conflict (overlap)
        
    Examples:
        >>> paths_conflict(Path("/a/b"), Path("/a/b/c"))
        True
        >>> paths_conflict(Path("/a/b"), Path("/a/c"))  
        False
        >>> paths_conflict(Path("/a/b"), Path("/a/b"))
        True
    """
    try:
        # Same path
        if path1 == path2:
            return True
        
        # Check if one is a parent of the other
        try:
            path1.relative_to(path2)
            return True  # path1 is under path2
        except ValueError:
            pass
        
        try:
            path2.relative_to(path1)
            return True  # path2 is under path1
        except ValueError:
            pass
        
        return False
        
    except (OSError, ValueError):
        # Error comparing paths - assume no conflict
        return False


def detect_path_conflicts(tool_calls: List[ToolCall]) -> bool:
    """Detect if tool calls have conflicting file path operations.
    
    Args:
        tool_calls: List of tool calls to check
        
    Returns:
        True if any paths conflict, False otherwise
    """
    if len(tool_calls) < 2:
        return False
    
    # Extract all paths from write tools
    all_paths = []
    for tool_call in tool_calls:
        paths = extract_paths(tool_call)
        all_paths.extend(paths)
    
    if len(all_paths) < 2:
        return False
    
    # Check all pairs for conflicts
    for i, path1 in enumerate(all_paths):
        for path2 in all_paths[i+1:]:
            if paths_conflict(path1, path2):
                return True
    
    return False


def has_write_conflicts(tool_calls: List[ToolCall]) -> bool:
    """Check if tool calls have write conflicts requiring sequential execution.
    
    This is the main function used by the parallel executor to decide
    whether to run tools in parallel or fall back to sequential.
    
    Args:
        tool_calls: List of tool calls to analyze
        
    Returns:
        True if conflicts detected and sequential execution is needed
    """
    return detect_path_conflicts(tool_calls)


def group_by_conflicts(tool_calls: List[ToolCall]) -> List[List[ToolCall]]:
    """Group tool calls into conflict-free batches.
    
    This can be used for more sophisticated scheduling where some tools
    can run in parallel while others must be sequential.
    
    Args:
        tool_calls: Tool calls to group
        
    Returns:
        List of batches where each batch has no internal conflicts
    """
    if not tool_calls:
        return []
    
    if len(tool_calls) == 1:
        return [tool_calls]
    
    # Simple greedy algorithm: create batches sequentially
    batches = []
    remaining = tool_calls.copy()
    
    while remaining:
        current_batch = [remaining.pop(0)]
        
        # Try to add more tools to current batch
        i = 0
        while i < len(remaining):
            candidate = remaining[i]
            
            # Check if candidate conflicts with any tool in current batch
            test_batch = current_batch + [candidate]
            if not detect_path_conflicts(test_batch):
                current_batch.append(remaining.pop(i))
            else:
                i += 1
        
        batches.append(current_batch)
    
    return batches
