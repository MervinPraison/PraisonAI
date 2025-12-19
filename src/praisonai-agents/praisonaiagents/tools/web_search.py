"""Unified web search tool with automatic fallback across multiple providers.

This module provides a single `search_web` function that automatically tries
multiple search providers in order, falling back to the next if one fails.

Search Provider Priority:
1. Tavily (requires TAVILY_API_KEY + tavily-python)
2. Exa (requires EXA_API_KEY + exa_py)
3. You.com (requires YDC_API_KEY + youdotcom)
4. DuckDuckGo (requires duckduckgo_search package, no API key)
5. SearxNG (requires requests + running SearxNG instance)

Usage:
    from praisonaiagents.tools import search_web
    
    # Simple search - automatically uses best available provider
    results = search_web("AI news 2024")
    
    # With max results
    results = search_web("Python tutorials", max_results=10)
"""

from typing import List, Dict, Any, Optional
import logging
import os
from importlib import util

logger = logging.getLogger(__name__)


def _check_tavily() -> tuple[bool, Optional[str]]:
    """Check if Tavily is available."""
    if util.find_spec("tavily") is None:
        return False, "tavily-python package not installed"
    if not os.environ.get("TAVILY_API_KEY"):
        return False, "TAVILY_API_KEY not set"
    return True, None


def _check_exa() -> tuple[bool, Optional[str]]:
    """Check if Exa is available."""
    if util.find_spec("exa_py") is None:
        return False, "exa_py package not installed"
    if not os.environ.get("EXA_API_KEY"):
        return False, "EXA_API_KEY not set"
    return True, None


def _check_youdotcom() -> tuple[bool, Optional[str]]:
    """Check if You.com is available."""
    if util.find_spec("youdotcom") is None:
        return False, "youdotcom package not installed"
    if not os.environ.get("YDC_API_KEY"):
        return False, "YDC_API_KEY not set"
    return True, None


def _check_duckduckgo() -> tuple[bool, Optional[str]]:
    """Check if DuckDuckGo is available."""
    if util.find_spec("duckduckgo_search") is None:
        return False, "duckduckgo_search package not installed"
    return True, None


def _check_searxng() -> tuple[bool, Optional[str]]:
    """Check if SearxNG is available."""
    if util.find_spec("requests") is None:
        return False, "requests package not installed"
    return True, None


def _search_tavily(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using Tavily."""
    from tavily import TavilyClient
    
    client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
    response = client.search(query=query, max_results=max_results)
    
    results = []
    for r in response.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", ""),
            "provider": "tavily"
        })
    return results


def _search_exa(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using Exa."""
    from exa_py import Exa
    
    client = Exa(os.environ.get("EXA_API_KEY"))
    response = client.search(query=query, num_results=max_results)
    
    results = []
    for r in response.results:
        results.append({
            "title": getattr(r, "title", "") or "",
            "url": r.url,
            "snippet": getattr(r, "text", "") or "",
            "provider": "exa"
        })
    return results


def _search_youdotcom(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using You.com."""
    from youdotcom import You
    
    client = You(api_key_auth=os.environ.get("YDC_API_KEY"))
    response = client.search.unified(query=query, count=max_results)
    
    results = []
    # Handle response object
    if hasattr(response, 'results'):
        web_results = getattr(response.results, 'web', []) or []
        for r in web_results[:max_results]:
            results.append({
                "title": getattr(r, "title", "") or "",
                "url": getattr(r, "url", "") or "",
                "snippet": getattr(r, "description", "") or "",
                "provider": "youdotcom"
            })
    elif isinstance(response, dict):
        web_results = response.get("results", {}).get("web", [])
        for r in web_results[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", ""),
                "provider": "youdotcom"
            })
    return results


def _search_duckduckgo(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using DuckDuckGo."""
    from duckduckgo_search import DDGS
    
    results = []
    ddgs = DDGS()
    for result in ddgs.text(keywords=query, max_results=max_results):
        results.append({
            "title": result.get("title", ""),
            "url": result.get("href", ""),
            "snippet": result.get("body", ""),
            "provider": "duckduckgo"
        })
    return results


def _search_searxng(query: str, max_results: int = 5, searxng_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search using SearxNG."""
    import requests
    
    url = searxng_url or os.environ.get("SEARXNG_URL", "http://localhost:32768/search")
    
    params = {
        'q': query,
        'format': 'json',
        'engines': 'google,bing,duckduckgo',
        'safesearch': '1'
    }
    
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    
    raw_results = response.json().get('results', [])
    
    results = []
    for result in raw_results[:max_results]:
        results.append({
            "title": result.get("title", ""),
            "url": result.get("url", ""),
            "snippet": result.get("content", ""),
            "provider": "searxng"
        })
    return results


# Provider configuration: (name, check_func, search_func)
SEARCH_PROVIDERS = [
    ("tavily", _check_tavily, _search_tavily),
    ("exa", _check_exa, _search_exa),
    ("youdotcom", _check_youdotcom, _search_youdotcom),
    ("duckduckgo", _check_duckduckgo, _search_duckduckgo),
    ("searxng", _check_searxng, _search_searxng),
]


def search_web(
    query: str,
    max_results: int = 5,
    providers: Optional[List[str]] = None,
    searxng_url: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search the web using multiple providers with automatic fallback.
    
    Tries each search provider in order until one succeeds. For each provider,
    it first checks if the API key is set (if required) and if the package is
    installed, then attempts the search. If the search fails, it moves to the
    next provider.
    
    Args:
        query: The search query string
        max_results: Maximum number of results to return (default: 5)
        providers: Optional list of provider names to try, in order.
                  If not specified, uses default order:
                  ["tavily", "exa", "youdotcom", "duckduckgo", "searxng"]
        searxng_url: Optional custom SearxNG instance URL
        
    Returns:
        List of search results, each containing:
        - title: Result title
        - url: Result URL
        - snippet: Result description/snippet
        - provider: Name of the provider that returned the result
        
        If all providers fail, returns a list with a single error dict.
        
    Example:
        # Use default provider order
        results = search_web("AI news 2024")
        
        # Specify providers to try
        results = search_web("Python tutorials", providers=["duckduckgo", "tavily"])
        
        # With custom SearxNG URL
        results = search_web("tech news", searxng_url="http://my-searxng:8080/search")
    """
    errors = []
    
    # Determine which providers to try
    if providers:
        # Filter to only valid provider names
        provider_order = []
        for name in providers:
            for pname, check_fn, search_fn in SEARCH_PROVIDERS:
                if pname == name.lower():
                    provider_order.append((pname, check_fn, search_fn))
                    break
    else:
        provider_order = SEARCH_PROVIDERS
    
    for provider_name, check_func, search_func in provider_order:
        # Step 1: Check if provider is available (API key + package)
        is_available, check_error = check_func()
        if not is_available:
            logger.debug(f"Skipping {provider_name}: {check_error}")
            errors.append(f"{provider_name}: {check_error}")
            continue
        
        # Step 2: Try to search
        try:
            logger.debug(f"Trying {provider_name} for query: {query}")
            
            if provider_name == "searxng":
                results = search_func(query, max_results, searxng_url)
            else:
                results = search_func(query, max_results)
            
            if results:
                logger.info(f"search_web: Successfully used {provider_name}")
                return results
            else:
                errors.append(f"{provider_name}: No results returned")
                
        except Exception as e:
            error_msg = f"{provider_name}: {str(e)}"
            logger.debug(f"Search failed with {provider_name}: {e}")
            errors.append(error_msg)
            continue
    
    # All providers failed
    error_summary = "; ".join(errors) if errors else "No search providers available"
    logger.error(f"search_web: All providers failed - {error_summary}")
    return [{"error": f"All search providers failed: {error_summary}"}]


def get_available_providers() -> List[Dict[str, Any]]:
    """Get list of available search providers and their status.
    
    Returns:
        List of dicts with provider info:
        - name: Provider name
        - available: Whether the provider is ready to use
        - reason: Reason if not available
        
    Example:
        providers = get_available_providers()
        for p in providers:
            print(f"{p['name']}: {'✓' if p['available'] else '✗'} {p.get('reason', '')}")
    """
    result = []
    for name, check_func, _ in SEARCH_PROVIDERS:
        is_available, error = check_func()
        result.append({
            "name": name,
            "available": is_available,
            "reason": error if not is_available else None
        })
    return result


if __name__ == "__main__":
    # Example usage and provider status check
    print("=" * 60)
    print("Web Search Tool - Provider Status")
    print("=" * 60)
    
    providers = get_available_providers()
    for p in providers:
        status = "✓ Available" if p["available"] else f"✗ {p['reason']}"
        print(f"  {p['name']:12} {status}")
    
    print("\n" + "=" * 60)
    print("Testing search_web...")
    print("=" * 60)
    
    results = search_web("Python programming", max_results=3)
    if results and "error" not in results[0]:
        print(f"\nFound {len(results)} results using {results[0].get('provider', 'unknown')}:")
        for r in results:
            print(f"\n  Title: {r.get('title', 'N/A')[:50]}...")
            print(f"  URL: {r.get('url', 'N/A')}")
    else:
        print(f"\nSearch failed: {results}")
