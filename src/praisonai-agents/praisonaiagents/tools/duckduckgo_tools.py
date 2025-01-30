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
from importlib import util

def internet_search(query: str) -> List[Dict]:
    """Perform an internet search using DuckDuckGo."""
    # Check if duckduckgo_search is installed
    if util.find_spec("duckduckgo_search") is None:
        error_msg = "DuckDuckGo search is not available. Please install duckduckgo_search package using: pip install duckduckgo_search"
        logging.error(error_msg)
        return [{"error": error_msg}]

    try:
        # Import only when needed
        from duckduckgo_search import DDGS
        results = []
        ddgs = DDGS()
        for result in ddgs.text(keywords=query, max_results=5):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "snippet": result.get("body", "")
            })
        return results

    except Exception as e:
        error_msg = f"Error during DuckDuckGo search: {e}"
        logging.error(error_msg)
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
