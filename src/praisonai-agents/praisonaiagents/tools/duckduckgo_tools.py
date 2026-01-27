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

def internet_search(query: str, max_results: int = 5, retries: int = MAX_RETRIES) -> List[Dict]:
    """Perform an internet search using DuckDuckGo with retry logic.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return (default: 5)
        retries: Number of retry attempts on failure (default: 3)
        
    Returns:
        List of search results with title, url, and snippet
    """
    # Check if duckduckgo_search is installed
    if util.find_spec("duckduckgo_search") is None:
        error_msg = "DuckDuckGo search is not available. Please install duckduckgo_search package using: pip install duckduckgo_search"
        logging.error(error_msg)
        return [{"error": error_msg}]

    last_error = None
    for attempt in range(retries):
        try:
            # Import only when needed
            from duckduckgo_search import DDGS
            results = []
            ddgs = DDGS()
            
            # Try text search
            search_results = list(ddgs.text(keywords=query, max_results=max_results))
            
            for result in search_results:
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", "")
                })
            
            # If we got results, return them
            if results:
                return results
            
            # Empty results - retry with backoff
            if attempt < retries - 1:
                logging.debug(f"DuckDuckGo returned empty results, retrying ({attempt + 1}/{retries})...")
                time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                
        except Exception as e:
            last_error = e
            logging.debug(f"DuckDuckGo search attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
    
    # All retries exhausted
    if last_error:
        error_msg = f"DuckDuckGo search failed after {retries} attempts: {last_error}"
    else:
        error_msg = f"DuckDuckGo search returned no results after {retries} attempts"
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
