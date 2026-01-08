"""
Context Building Utilities for RAG.

Provides token-aware context assembly with deduplication.
No heavy imports - only stdlib.
"""

import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple


def _estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.
    
    Uses simple heuristic: ~4 characters per token for English.
    This avoids importing tokenizers for lightweight operation.
    """
    return len(text) // 4 + 1


def _chunk_hash(text: str, source: Optional[str] = None) -> str:
    """
    Generate stable hash for chunk deduplication.
    
    Args:
        text: Chunk text content
        source: Optional source identifier
        
    Returns:
        Hash string for deduplication
    """
    content = f"{source or ''}:{text}"
    return hashlib.md5(content.encode()).hexdigest()[:16]


def deduplicate_chunks(
    results: List[Dict[str, Any]],
    similarity_threshold: float = 0.9,
) -> List[Dict[str, Any]]:
    """
    Deduplicate chunks by content hash.
    
    Args:
        results: List of search results with 'text' or 'memory' key
        similarity_threshold: Not used currently (hash-based dedup)
        
    Returns:
        Deduplicated list of results
    """
    seen_hashes: Set[str] = set()
    unique_results: List[Dict[str, Any]] = []
    
    for result in results:
        # Skip None results
        if result is None:
            continue
        # Handle different result formats
        text = result.get("text") or result.get("memory", "")
        # CRITICAL: Handle metadata=None from mem0 - ensure always dict
        metadata = result.get("metadata") or {}
        source = metadata.get("source", "")
        
        chunk_id = _chunk_hash(text, source)
        
        if chunk_id not in seen_hashes:
            seen_hashes.add(chunk_id)
            unique_results.append(result)
    
    return unique_results


def truncate_context(
    text: str,
    max_tokens: int,
    suffix: str = "\n\n[Context truncated...]",
) -> str:
    """
    Truncate context to fit within token budget.
    
    Args:
        text: Context text to truncate
        max_tokens: Maximum tokens allowed
        suffix: Suffix to add when truncated
        
    Returns:
        Truncated text
    """
    estimated_tokens = _estimate_tokens(text)
    
    if estimated_tokens <= max_tokens:
        return text
    
    # Calculate target character count
    suffix_tokens = _estimate_tokens(suffix)
    target_tokens = max_tokens - suffix_tokens
    target_chars = target_tokens * 4
    
    # Truncate at word boundary
    truncated = text[:target_chars]
    last_space = truncated.rfind(" ")
    if last_space > target_chars * 0.8:
        truncated = truncated[:last_space]
    
    return truncated + suffix


def build_context(
    results: List[Dict[str, Any]],
    max_tokens: int = 4000,
    deduplicate: bool = True,
    separator: str = "\n\n---\n\n",
    include_source: bool = True,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Build context string from retrieval results.
    
    Args:
        results: List of search results
        max_tokens: Maximum tokens for context
        deduplicate: Whether to deduplicate chunks
        separator: Separator between chunks
        include_source: Whether to include source info
        
    Returns:
        Tuple of (context_string, used_results)
    """
    if not results:
        return "", []
    
    # Deduplicate if requested
    if deduplicate:
        results = deduplicate_chunks(results)
    
    context_parts: List[str] = []
    used_results: List[Dict[str, Any]] = []
    current_tokens = 0
    separator_tokens = _estimate_tokens(separator)
    
    for i, result in enumerate(results):
        # Skip None results
        if result is None:
            continue
        # Handle different result formats
        text = result.get("text") or result.get("memory", "")
        if not text:
            continue
        
        # Build chunk text with optional source
        if include_source:
            # CRITICAL: Handle metadata=None from mem0 - ensure always dict
            metadata = result.get("metadata") or {}
            source = metadata.get("source", "")
            filename = metadata.get("filename", "")
            source_label = filename or source or f"Source {i + 1}"
            chunk_text = f"[{source_label}]\n{text}"
        else:
            chunk_text = text
        
        chunk_tokens = _estimate_tokens(chunk_text)
        
        # Check if we can fit this chunk
        if current_tokens + chunk_tokens + separator_tokens > max_tokens:
            # Try to fit partial chunk
            remaining_tokens = max_tokens - current_tokens - separator_tokens
            if remaining_tokens > 100:  # Only include if meaningful
                truncated = truncate_context(chunk_text, remaining_tokens, "...")
                context_parts.append(truncated)
                used_results.append(result)
            break
        
        context_parts.append(chunk_text)
        used_results.append(result)
        current_tokens += chunk_tokens + separator_tokens
    
    context = separator.join(context_parts)
    return context, used_results


class DefaultContextBuilder:
    """
    Default implementation of ContextBuilderProtocol.
    
    Provides token-aware context assembly with deduplication.
    """
    
    def __init__(
        self,
        separator: str = "\n\n---\n\n",
        include_source: bool = True,
    ):
        self.separator = separator
        self.include_source = include_source
    
    def build(
        self,
        results: List[Dict[str, Any]],
        max_tokens: int = 4000,
        deduplicate: bool = True,
    ) -> str:
        """Build context string from results."""
        context, _ = build_context(
            results=results,
            max_tokens=max_tokens,
            deduplicate=deduplicate,
            separator=self.separator,
            include_source=self.include_source,
        )
        return context
