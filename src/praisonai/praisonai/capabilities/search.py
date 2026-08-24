"""
Search Capabilities Module

Provides search functionality.
"""

from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List


@dataclass
class SearchResult:
    """Result from search operations."""
    results: List[Dict[str, Any]]
    query: str
    total: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def search(
    query: str,
    sources: Optional[List[str]] = None,
    max_results: int = 10,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> SearchResult:
    """
    Perform a search query.
    
    Args:
        query: Search query
        sources: Optional list of sources to search
        max_results: Maximum number of results
        timeout: Request timeout in seconds
        api_key: Optional API key override
        api_base: Optional API base URL override
        metadata: Optional metadata for tracing
        
    Returns:
        SearchResult with search results
        
    Example:
        >>> result = search("What is AI?")
        >>> for r in result.results:
        ...     print(r['title'], r['url'])
    """
    # Search is backed by the DuckDuckGo tool shipped with praisonaiagents.
    from praisonaiagents.tools.duckduckgo_tools import internet_search

    search_results = internet_search(query, max_results=max_results)

    results = []
    if isinstance(search_results, list):
        for item in search_results:
            if 'error' in item:
                raise RuntimeError(item['error'])
            results.append({
                'title': item.get('title', ''),
                'url': item.get('href', item.get('url', '')),
                'snippet': item.get('body', item.get('snippet', '')),
            })
    elif isinstance(search_results, str):
        results.append({
            'title': 'Search Result',
            'url': '',
            'snippet': search_results,
        })

    return SearchResult(
        results=results,
        query=query,
        total=len(results),
        metadata=metadata or {},
    )


async def asearch(
    query: str,
    sources: Optional[List[str]] = None,
    max_results: int = 10,
    timeout: float = 600.0,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> SearchResult:
    """
    Async: Perform a search query.
    
    See search() for full documentation.
    """
    # For now, delegate to sync version
    return search(
        query=query,
        sources=sources,
        max_results=max_results,
        timeout=timeout,
        api_key=api_key,
        api_base=api_base,
        metadata=metadata,
        **kwargs
    )
