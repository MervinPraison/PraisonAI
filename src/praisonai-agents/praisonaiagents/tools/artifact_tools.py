"""
Artifact retrieval tools for accessing spilled tool outputs.

These tools are registered lazily when an artifact overflow occurs,
providing agents with the ability to page through preserved outputs.
"""

import logging
import threading
from typing import Optional, List, Dict, Any

from ..context.artifacts import ArtifactRef, GrepMatch
from .decorator import tool


# Thread-local storage for per-agent artifact stores
_artifact_stores = threading.local()


def set_artifact_store(store, agent_id: Optional[str] = None):
    """Set the artifact store for retrieval tools.
    
    Args:
        store: The artifact store instance
        agent_id: Optional agent identifier for multi-agent scenarios
    """
    if not hasattr(_artifact_stores, 'stores'):
        _artifact_stores.stores = {}
    
    # Use agent_id as key, or 'default' if not provided
    key = agent_id or 'default'
    _artifact_stores.stores[key] = store


def _get_artifact_store(agent_id: Optional[str] = None):
    """Get the artifact store for the current context."""
    if not hasattr(_artifact_stores, 'stores'):
        return None
    
    # Try agent-specific store first, then fall back to default
    key = agent_id or 'default'
    stores = _artifact_stores.stores
    return stores.get(key) or stores.get('default')


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
    _artifact_store = _get_artifact_store()
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
    _artifact_store = _get_artifact_store()
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
    _artifact_store = _get_artifact_store()
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
    _artifact_store = _get_artifact_store()
    if _artifact_store is None:
        return "Error: Artifact store not available"
    
    try:
        # Try to load metadata to get correct mime_type and checksum
        import json
        from pathlib import Path
        
        meta_path = artifact_path.replace(".artifact", ".meta.json")
        meta = {}
        try:
            p = Path(meta_path)
            if p.exists():
                meta = json.loads(p.read_text())
        except Exception:
            pass
        
        # Create ref with actual metadata
        ref = ArtifactRef(
            path=artifact_path,
            summary=meta.get("summary", ""),
            size_bytes=meta.get("size_bytes", 0),
            mime_type=meta.get("mime_type", "text/plain"),
            checksum=meta.get("checksum", ""),
            artifact_id=meta.get("artifact_id", ""),
            agent_id=meta.get("agent_id", ""),
            run_id=meta.get("run_id", ""),
            tool_name=meta.get("tool_name"),
            turn_id=meta.get("turn_id", 0)
        )
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