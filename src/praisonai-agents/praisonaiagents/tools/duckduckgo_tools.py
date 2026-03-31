"""DuckDuckGo search functionality.

Usage:
from praisonaiagents.tools import internet_search
results = internet_search("AI news")

or 
from praisonaiagents.tools import duckduckgo
results = duckduckgo("AI news")
"""

from typing import List, Dict
import logging
import time
from importlib import util

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds

from praisonaiagents.utils.resilience import retry_with_backoff

@retry_with_backoff(retries=3, backoff_in_seconds=1.0, exceptions=(Exception,), jitter_factor=0.25)
def _do_duckduckgo_search(query: str, max_results: int) -> List[Dict]:
    """Inner core logic wrapped by resilience decorator."""
    from ddgs import DDGS
    results = []
    ddgs = DDGS()
    
    # Try text search (use positional 'query' for v8+ compatibility)
    search_results = list(ddgs.text(query, max_results=max_results))
    
    for result in search_results:
        results.append({
            "title": result.get("title", ""),
            "url": result.get("href", ""),
            "snippet": result.get("body", "")
        })
    
    # If we got results, return them
    if results:
        return results
        
    raise Exception("DuckDuckGo returned empty results")


def internet_search(query: str, max_results: int = 5, retries: int = MAX_RETRIES) -> List[Dict]:
    """Perform an internet search using DuckDuckGo with retry logic.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return (default: 5)
        retries: Number of retry attempts on failure (default: 3)
        
    Returns:
        List of search results with title, url, and snippet
    """
    # Check if ddgs is installed
    if util.find_spec("ddgs") is None:
        error_msg = "DuckDuckGo search is not available. Please install ddgs package using: pip install ddgs"
        logging.error(error_msg)
        return [{"error": error_msg}]

    try:
        return _do_duckduckgo_search(query, max_results)
    except Exception as e:
        error_msg = f"DuckDuckGo search failed: {str(e)}"
        logging.warning(error_msg)
        return [{"error": error_msg}]

def duckduckgo(query: str) -> List[Dict]:
    """Alias for internet_search function."""
    return internet_search(query)

if __name__ == "__main__":
    # Example usage
    results = internet_search("Python programming")
    for result in results:
        print(f"\nTitle: {result.get('title')}")
        print(f"URL: {result.get('url')}")
        print(f"Snippet: {result.get('snippet')}")
