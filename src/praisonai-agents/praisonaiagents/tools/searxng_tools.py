"""SearxNG search functionality.

Usage:
from praisonaiagents.tools import searxng_search
results = searxng_search("AI news")

or 
from praisonaiagents.tools import searxng
results = searxng("AI news")
"""

from typing import List, Dict, Optional
import logging
from importlib import util

def searxng_search(
    query: str, 
    max_results: int = 5,
    searxng_url: Optional[str] = None
) -> List[Dict]:
    """Perform an internet search using SearxNG instance.
    
    Args:
        query: Search query string
        max_results: Maximum number of results to return
        searxng_url: SearxNG instance URL (defaults to localhost:32768)
        
    Returns:
        List[Dict]: Search results with title, url, and snippet keys
                   Returns error dict on failure
    """
    # Check if requests is available
    if util.find_spec("requests") is None:
        error_msg = "SearxNG search requires requests package. Install with: pip install requests"
        logging.error(error_msg)
        return [{"error": error_msg}]
    
    try:
        import requests
        
        # Default URL for local SearxNG instance
        url = searxng_url or "http://localhost:32768/search"
        
        params = {
            'q': query, 
            'format': 'json',
            'engines': 'google,bing,duckduckgo',  # Multiple engines
            'safesearch': '1'  # Safe search enabled
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        raw_results = response.json().get('results', [])
        
        # Standardize to PraisonAI format
        results = []
        for i, result in enumerate(raw_results[:max_results]):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("content", "")
            })
            
        return results
        
    except requests.exceptions.ConnectionError:
        error_msg = f"Could not connect to SearxNG at {url}. Ensure SearxNG is running."
        logging.error(error_msg)
        return [{"error": error_msg}]
    except requests.exceptions.Timeout:
        error_msg = "SearxNG search request timed out"
        logging.error(error_msg)
        return [{"error": error_msg}]
    except requests.exceptions.RequestException as e:
        error_msg = f"SearxNG search request failed: {e}"
        logging.error(error_msg)
        return [{"error": error_msg}]
    except (ValueError, KeyError) as e:
        error_msg = f"Error parsing SearxNG response: {e}"
        logging.error(error_msg)
        return [{"error": error_msg}]

def searxng(query: str, max_results: int = 5, searxng_url: Optional[str] = None) -> List[Dict]:
    """Alias for searxng_search function."""
    return searxng_search(query, max_results, searxng_url)

if __name__ == "__main__":
    # Example usage
    results = searxng_search("Python programming")
    for result in results:
        print(f"\nTitle: {result.get('title')}")
        print(f"URL: {result.get('url')}")
        print(f"Snippet: {result.get('snippet')}")