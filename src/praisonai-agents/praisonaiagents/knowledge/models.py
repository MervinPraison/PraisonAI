"""
Knowledge Models for PraisonAI Agents.

Typed dataclasses for knowledge retrieval results.
These models guarantee metadata is ALWAYS a dict (never None).

No heavy imports - only stdlib.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SearchResultItem:
    """
    A single search result item with guaranteed schema.
    
    CRITICAL: metadata is ALWAYS a dict, never None.
    This is enforced at construction time.
    
    Attributes:
        id: Unique identifier for the result
        text: The text content (normalized from 'memory' field if needed)
        score: Relevance score (default 0.0)
        metadata: Additional metadata (ALWAYS dict, never None)
        source: Optional source identifier
        filename: Optional filename
        created_at: Optional creation timestamp
        updated_at: Optional update timestamp
    """
    id: str = ""
    text: str = ""
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    filename: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    def __post_init__(self):
        """Ensure metadata is never None."""
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "id": self.id,
            "text": self.text,
            "score": self.score,
            "metadata": self.metadata,
            "source": self.source,
            "filename": self.filename,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SearchResult:
    """
    Container for search results with guaranteed schema.
    
    Attributes:
        results: List of SearchResultItem objects
        metadata: Additional metadata about the search (ALWAYS dict)
        query: The original query string
        total_count: Total number of results (may differ from len(results) if paginated)
    """
    results: List[SearchResultItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    query: str = ""
    total_count: Optional[int] = None
    
    def __post_init__(self):
        """Ensure metadata is never None."""
        if self.metadata is None:
            self.metadata = {}
        if self.results is None:
            self.results = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format compatible with legacy code."""
        return {
            "results": [r.to_dict() if hasattr(r, 'to_dict') else r for r in self.results],
            "metadata": self.metadata,
            "query": self.query,
            "total_count": self.total_count or len(self.results),
        }
    
    def to_legacy_format(self) -> Dict[str, Any]:
        """
        Convert to legacy format for backward compatibility.
        
        Returns dict with 'results' key containing list of dicts.
        """
        return {
            "results": [
                {
                    "id": r.id,
                    "memory": r.text,  # Legacy field name
                    "text": r.text,
                    "score": r.score,
                    "metadata": r.metadata,
                    "source": r.source,
                    "filename": r.filename,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in self.results
            ]
        }


@dataclass
class AddResult:
    """
    Result of adding content to knowledge store.
    
    Attributes:
        id: ID of the added item
        success: Whether the operation succeeded
        message: Optional message about the operation
        metadata: Additional metadata (ALWAYS dict)
    """
    id: str = ""
    success: bool = True
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Ensure metadata is never None."""
        if self.metadata is None:
            self.metadata = {}


def normalize_search_item(raw: Dict[str, Any]) -> SearchResultItem:
    """
    Normalize a raw search result item to SearchResultItem.
    
    This is the SINGLE canonical normalization function.
    Handles mem0 format, internal format, and any other variations.
    
    CRITICAL: Ensures metadata is ALWAYS a dict, never None.
    
    Args:
        raw: Raw result dict from any backend
        
    Returns:
        SearchResultItem with guaranteed schema
    """
    if raw is None:
        return SearchResultItem()
    
    # Handle text field (mem0 uses 'memory', others use 'text')
    text = raw.get("text") or raw.get("memory", "") or ""
    
    # Handle metadata - CRITICAL: ensure never None
    metadata = raw.get("metadata")
    if metadata is None:
        metadata = {}
    elif not isinstance(metadata, dict):
        metadata = {}
    
    # Extract source/filename from metadata if not at top level
    source = raw.get("source") or metadata.get("source")
    filename = raw.get("filename") or metadata.get("filename")
    
    return SearchResultItem(
        id=str(raw.get("id", "")),
        text=str(text),
        score=float(raw.get("score", 0.0) or 0.0),
        metadata=metadata,
        source=source,
        filename=filename,
        created_at=raw.get("created_at"),
        updated_at=raw.get("updated_at"),
    )


def normalize_search_result(raw: Any) -> SearchResult:
    """
    Normalize raw search results to SearchResult.
    
    Handles various input formats:
    - dict with 'results' key (mem0 format)
    - list of results
    - single result dict
    - None
    
    Args:
        raw: Raw search results from any backend
        
    Returns:
        SearchResult with guaranteed schema
    """
    if raw is None:
        return SearchResult()
    
    # Handle dict with 'results' key
    if isinstance(raw, dict):
        if "results" in raw:
            items = raw.get("results", []) or []
            normalized_items = [
                normalize_search_item(item) 
                for item in items 
                if item is not None
            ]
            return SearchResult(
                results=normalized_items,
                metadata=raw.get("metadata") or {},
                query=raw.get("query", ""),
            )
        else:
            # Single result dict
            return SearchResult(
                results=[normalize_search_item(raw)],
                metadata={},
            )
    
    # Handle list of results
    if isinstance(raw, list):
        normalized_items = [
            normalize_search_item(item) 
            for item in raw 
            if item is not None
        ]
        return SearchResult(results=normalized_items)
    
    # Fallback
    return SearchResult()


def normalize_to_dict(raw: Any) -> Dict[str, Any]:
    """
    Normalize raw search results to legacy dict format.
    
    Convenience function for code that expects dict format.
    Ensures all items have metadata as dict (never None).
    
    Args:
        raw: Raw search results from any backend
        
    Returns:
        Dict with 'results' key containing normalized items
    """
    result = normalize_search_result(raw)
    return result.to_legacy_format()
