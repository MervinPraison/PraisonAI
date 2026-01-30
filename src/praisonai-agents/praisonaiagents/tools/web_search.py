"""Unified web search tool with automatic fallback across multiple providers.

This module provides a single `search_web` function that automatically tries
multiple search providers in order, falling back to the next if one fails.

Search Provider Priority:
1. Tavily (requires TAVILY_API_KEY + tavily-python)
2. Brave (requires BRAVE_API_KEY + requests)
3. Exa (requires EXA_API_KEY + exa_py)
4. You.com (requires YDC_API_KEY + youdotcom)
5. DuckDuckGo (requires duckduckgo_search package, no API key)
6. SearxNG (requires requests + running SearxNG instance)

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


def _check_brave() -> tuple[bool, Optional[str]]:
    """Check if Brave Search is available."""
    if not os.environ.get("BRAVE_API_KEY"):
        return False, "BRAVE_API_KEY not set"
    if util.find_spec("requests") is None:
        return False, "requests package not installed"
    return True, None


def _check_searxng() -> tuple[bool, Optional[str]]:
    """Check if SearxNG is available."""
    if util.find_spec("requests") is None:
        return False, "requests package not installed"
    return True, None


def _search_tavily(query: str, max_results: int = 5, search_depth: str = "basic", raw_content: bool = False) -> List[Dict[str, Any]]:
    """Search using Tavily."""
    from tavily import TavilyClient
    
    client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
    depth = os.environ.get("TAVILY_SEARCH_DEPTH", search_depth).lower()
    if depth not in ("basic", "advanced"):
        depth = "basic"
    response = client.search(
        query=query, 
        max_results=max_results, 
        search_depth=depth,
        include_raw_content=raw_content
    )
    
    results = []
    for r in response.get("results", []):
        snippet = r.get("raw_content", "") if raw_content else r.get("content", "")
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": snippet,
            "provider": "tavily"
        })
    return results


def _search_exa(query: str, max_results: int = 5, full_text: bool = True) -> List[Dict[str, Any]]:
    """Search using Exa.
    
    Args:
        full_text: True for full page text (more tokens), False for highlights only.
    """
    from exa_py import Exa
    
    client = Exa(os.environ.get("EXA_API_KEY"))
    response = client.search(query=query, num_results=max_results, text=full_text)
    
    results = []
    for r in response.results:
        snippet = getattr(r, "text", "") if full_text else getattr(r, "highlights", [""])[0] if getattr(r, "highlights", None) else ""
        results.append({
            "title": getattr(r, "title", "") or "",
            "url": r.url,
            "snippet": snippet or "",
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
            description = getattr(r, "description", "") or ""
            snippets = getattr(r, "snippets", []) or []
            full_snippet = description
            if snippets:
                full_snippet += "\n" + "\n".join(snippets)
                
            results.append({
                "title": getattr(r, "title", "") or "",
                "url": getattr(r, "url", "") or "",
                "snippet": full_snippet.strip(),
                "provider": "youdotcom"
            })
    elif isinstance(response, dict):
        web_results = response.get("results", {}).get("web", [])
        for r in web_results[:max_results]:
            description = r.get("description", "")
            snippets = r.get("snippets", [])
            full_snippet = description
            if snippets:
                full_snippet += "\n" + "\n".join(snippets)
                
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": full_snippet.strip(),
                "provider": "youdotcom"
            })
    return results


def _search_brave(query: str, max_results: int = 5, extra_snippets: bool = True) -> List[Dict[str, Any]]:
    """Search using Brave Search.
    
    Args:
        extra_snippets: Include extra snippets for richer content (True by default).
    """
    import requests
    
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": os.environ.get("BRAVE_API_KEY")
    }
    params = {
        "q": query, 
        "count": max_results,
        "result_filter": "web"
    }
    
    response = requests.get(url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    results = []
    for r in data.get("web", {}).get("results", []):
        description = r.get("description", "")
        full_snippet = description
        
        if extra_snippets:
            extra = r.get("extra_snippets", [])
            if extra:
                full_snippet += "\n" + "\n".join(extra)
            
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": full_snippet.strip(),
            "provider": "brave"
        })
    return results


def _search_duckduckgo(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search using DuckDuckGo with retry logic."""
    import time
    from duckduckgo_search import DDGS
    
    max_retries = 3
    retry_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            results = []
            ddgs = DDGS()
            search_results = list(ddgs.text(keywords=query, max_results=max_results))
            
            for result in search_results:
                results.append({
                    "title": result.get("title", ""),
                    "url": result.get("href", ""),
                    "snippet": result.get("body", ""),
                    "provider": "duckduckgo"
                })
            
            if results:
                return results
            
            # Empty results - retry
            if attempt < max_retries - 1:
                logger.debug(f"DuckDuckGo returned empty, retrying ({attempt + 1}/{max_retries})...")
                time.sleep(retry_delay * (attempt + 1))
                
        except Exception as e:
            logger.debug(f"DuckDuckGo attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
            else:
                raise  # Re-raise on final attempt
    
    return []  # All retries exhausted with empty results


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
    ("brave", _check_brave, _search_brave),
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
    search_depth: str = "basic",
    tavily_raw_content: bool = False,
    exa_full_text: bool = True,
    brave_extra_snippets: bool = True,
) -> List[Dict[str, Any]]:
    """Search the web using one or more providers with automatic fallback.
    
    VALID PROVIDER NAMES: tavily, brave, exa, youdotcom, duckduckgo, searxng
    
    Args:
        query: Search query string
        max_results: Maximum results to return (default: 5)
        providers: Which provider(s) to use. Accepts:
                   - Single string: "tavily" (uses just that provider)
                   - Comma-separated: "tavily, brave" (tries in order, falls back on failure)
                   - List: ["tavily", "brave"] (same as comma-separated)
                   If not specified, tries all providers in order until one succeeds.
        
        Provider-specific options (only used by their respective provider):
        - searxng_url: [SearxNG] Custom instance URL
        - search_depth: [Tavily] "basic" (1 credit) or "advanced" (2 credits)
        - tavily_raw_content: [Tavily] Include full page content (default: False for snippets)
        - exa_full_text: [Exa] Full page text (True) vs highlights (False)
        - brave_extra_snippets: [Brave] Include extra snippets (True) for richer content
        
    Returns:
        List of dicts with: title, url, snippet, provider. Returns error dict if all fail.
    """
    errors = []
    
    # Valid provider names for reference
    valid_provider_names = [p[0] for p in SEARCH_PROVIDERS]
    
    # Check for WEB_SEARCH_PROVIDER env var (set by CLI --web-provider flag)
    if providers is None:
        env_provider = os.environ.get("WEB_SEARCH_PROVIDER")
        if env_provider:
            providers = env_provider
            logger.debug(f"Using provider from WEB_SEARCH_PROVIDER env var: {env_provider}")
    
    # Determine which providers to try
    if providers:
        # Handle string input (LLM might pass "provider1, provider2" instead of list)
        if isinstance(providers, str):
            providers = [p.strip() for p in providers.split(",")]
        
        # Filter to only valid provider names
        provider_order = []
        for name in providers:
            name_lower = name.lower().strip()
            matched = False
            for pname, check_fn, search_fn in SEARCH_PROVIDERS:
                if pname == name_lower:
                    provider_order.append((pname, check_fn, search_fn))
                    matched = True
                    break
            if not matched:
                logger.warning(f"Invalid provider '{name}'. Valid providers: {valid_provider_names}")
        
        # If no valid providers specified, fall back to default order
        if not provider_order:
            logger.warning(f"No valid providers in {providers}. Using default order: {valid_provider_names}")
            provider_order = SEARCH_PROVIDERS
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
            elif provider_name == "tavily":
                results = _search_tavily(query, max_results, search_depth, tavily_raw_content)
            elif provider_name == "exa":
                results = _search_exa(query, max_results, exa_full_text)
            elif provider_name == "brave":
                results = _search_brave(query, max_results, brave_extra_snippets)
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
