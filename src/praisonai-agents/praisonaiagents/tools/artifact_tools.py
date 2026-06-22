"""
Artifact retrieval tools for accessing spilled tool outputs.

These tools are registered lazily when an artifact overflow occurs,
providing agents with the ability to page through preserved outputs.
"""

import logging
from typing import Optional, List, Dict, Any

from ..context.artifacts import ArtifactRef, GrepMatch
from .decorator import tool


# Module-level artifact store reference
_artifact_store = None


def set_artifact_store(store):
    """Set the global artifact store for retrieval tools."""
    global _artifact_store
    _artifact_store = store


@tool("artifact_head")
def artifact_head(
    artifact_path: str,
    lines: int = 50
) -> str:
    """
    Get the first N lines of a stored artifact.
    
    Args:
        artifact_path: Path to the artifact (from ArtifactRef)
        lines: Number of lines to return (default: 50)
    
    Returns:
        First N lines of the artifact content
    """
    if _artifact_store is None:
        return "Error: Artifact store not available"
    
    try:
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0, mime_type="text/plain")
        return _artifact_store.head(ref, lines=lines)
    except Exception as e:
        logging.error(f"Failed to get artifact head: {e}")
        return f"Error reading artifact: {str(e)}"


@tool("artifact_tail")
def artifact_tail(
    artifact_path: str,
    lines: int = 50
) -> str:
    """
    Get the last N lines of a stored artifact.
    
    Args:
        artifact_path: Path to the artifact (from ArtifactRef)
        lines: Number of lines to return (default: 50)
    
    Returns:
        Last N lines of the artifact content
    """
    if _artifact_store is None:
        return "Error: Artifact store not available"
    
    try:
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0, mime_type="text/plain")
        return _artifact_store.tail(ref, lines=lines)
    except Exception as e:
        logging.error(f"Failed to get artifact tail: {e}")
        return f"Error reading artifact: {str(e)}"


@tool("artifact_grep")
def artifact_grep(
    artifact_path: str,
    pattern: str,
    context_lines: int = 2,
    max_matches: int = 50
) -> List[Dict[str, Any]]:
    """
    Search for a pattern in a stored artifact.
    
    Args:
        artifact_path: Path to the artifact (from ArtifactRef)
        pattern: Regex pattern to search for
        context_lines: Number of context lines before/after match (default: 2)
        max_matches: Maximum number of matches to return (default: 50)
    
    Returns:
        List of matches with line numbers and context
    """
    if _artifact_store is None:
        return [{"error": "Artifact store not available"}]
    
    try:
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0, mime_type="text/plain")
        matches = _artifact_store.grep(ref, pattern, context_lines=context_lines, max_matches=max_matches)
        
        # Convert to serializable format
        result = []
        for match in matches:
            result.append({
                "line_number": match.line_number,
                "line": match.line_content,
                "context_before": match.context_before,
                "context_after": match.context_after,
            })
        
        return result
    except Exception as e:
        logging.error(f"Failed to grep artifact: {e}")
        return [{"error": f"Error searching artifact: {str(e)}"}]


@tool("artifact_chunk")
def artifact_chunk(
    artifact_path: str,
    start_line: int = 1,
    end_line: Optional[int] = None
) -> str:
    """
    Get a chunk of lines from a stored artifact.
    
    Args:
        artifact_path: Path to the artifact (from ArtifactRef)
        start_line: Starting line number (1-indexed)
        end_line: Ending line number (inclusive), None for end of file
    
    Returns:
        Lines from start_line to end_line
    """
    if _artifact_store is None:
        return "Error: Artifact store not available"
    
    try:
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0, mime_type="text/plain")
        return _artifact_store.chunk(ref, start_line=start_line, end_line=end_line)
    except Exception as e:
        logging.error(f"Failed to get artifact chunk: {e}")
        return f"Error reading artifact: {str(e)}"


@tool("artifact_load")
def artifact_load(
    artifact_path: str
) -> Any:
    """
    Load the full content of a stored artifact.
    
    WARNING: This loads the entire artifact into memory.
    For large artifacts, consider using head/tail/grep/chunk instead.
    
    Args:
        artifact_path: Path to the artifact (from ArtifactRef)
    
    Returns:
        Full artifact content (deserialized if JSON)
    """
    if _artifact_store is None:
        return "Error: Artifact store not available"
    
    try:
        ref = ArtifactRef(path=artifact_path, summary="", size_bytes=0, mime_type="text/plain")
        return _artifact_store.load(ref)
    except Exception as e:
        logging.error(f"Failed to load artifact: {e}")
        return f"Error loading artifact: {str(e)}"


@tool("artifact_list")
def artifact_list(
    agent_id: Optional[str] = None,
    run_id: Optional[str] = None,
    tool_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List available artifacts matching the given filters.
    
    Args:
        agent_id: Filter by agent ID
        run_id: Filter by run ID
        tool_name: Filter by tool that created the artifact
    
    Returns:
        List of artifact metadata dictionaries
    """
    if _artifact_store is None:
        return [{"error": "Artifact store not available"}]
    
    try:
        refs = _artifact_store.list_artifacts(
            agent_id=agent_id,
            run_id=run_id,
            tool_name=tool_name
        )
        
        result = []
        for ref in refs:
            result.append({
                "path": ref.path,
                "artifact_id": ref.artifact_id,
                "size_bytes": ref.size_bytes,
                "created_at": ref.created_at,
                "tool_name": ref.tool_name,
                "summary": ref.summary,
            })
        
        return result
    except Exception as e:
        logging.error(f"Failed to list artifacts: {e}")
        return [{"error": f"Error listing artifacts: {str(e)}"}]