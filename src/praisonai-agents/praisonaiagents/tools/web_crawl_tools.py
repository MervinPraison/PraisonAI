"""Unified web crawling tool with provider fallback.

Similar to search_web, this tool auto-detects available providers and uses the best one.

Provider priority:
1. Tavily Extract (TAVILY_API_KEY) - highest quality
2. Crawl4AI (no API key needed, but requires crawl4ai package)
3. Spider (SPIDER_API_KEY)
4. Basic HTTP fetch (fallback, no dependencies)

Usage:
    from praisonaiagents.tools import web_crawl, crawl_web
    
    # Crawl a URL
    content = web_crawl("https://example.com")
    
    # Crawl multiple URLs
    contents = web_crawl(["https://example.com", "https://example.org"])
"""

import os
import logging
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


def _get_available_crawl_providers() -> List[str]:
    """Get list of available crawl providers based on installed packages and API keys."""
    providers = []
    
    # Check Tavily
    if os.environ.get("TAVILY_API_KEY"):
        try:
            from importlib import util
            if util.find_spec("tavily") is not None:
                providers.append("tavily")
        except ImportError:
            pass
    
    # Check Crawl4AI (no API key needed)
    try:
        from importlib import util
        if util.find_spec("crawl4ai") is not None:
            providers.append("crawl4ai")
    except ImportError:
        pass
    
    # Check Spider
    if os.environ.get("SPIDER_API_KEY"):
        providers.append("spider")
    
    # Basic HTTP fetch is always available
    providers.append("httpx")
    
    return providers


def _crawl_with_tavily(urls: List[str]) -> List[Dict[str, Any]]:
    """Crawl URLs using Tavily Extract."""
    from tavily import TavilyClient
    
    client = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))
    results = []
    
    for url in urls:
        try:
            response = client.extract(urls=[url])
            if response and response.get("results"):
                result = response["results"][0]
                results.append({
                    "url": url,
                    "content": result.get("raw_content", ""),
                    "title": result.get("title", ""),
                    "provider": "tavily",
                })
            else:
                results.append({
                    "url": url,
                    "content": "",
                    "error": "No content extracted",
                    "provider": "tavily",
                })
        except Exception as e:
            results.append({
                "url": url,
                "content": "",
                "error": str(e),
                "provider": "tavily",
            })
    
    return results


def _crawl_with_crawl4ai(urls: List[str]) -> List[Dict[str, Any]]:
    """Crawl URLs using Crawl4AI."""
    import asyncio
    from crawl4ai import AsyncWebCrawler
    
    async def _crawl_async():
        results = []
        async with AsyncWebCrawler() as crawler:
            for url in urls:
                try:
                    result = await crawler.arun(url=url)
                    results.append({
                        "url": url,
                        "content": result.markdown if hasattr(result, 'markdown') else str(result),
                        "title": result.title if hasattr(result, 'title') else "",
                        "provider": "crawl4ai",
                    })
                except Exception as e:
                    results.append({
                        "url": url,
                        "content": "",
                        "error": str(e),
                        "provider": "crawl4ai",
                    })
        return results
    
    # Run async crawler
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If we're already in an async context, create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _crawl_async())
                return future.result()
        else:
            return loop.run_until_complete(_crawl_async())
    except RuntimeError:
        return asyncio.run(_crawl_async())


def _crawl_with_httpx(urls: List[str]) -> List[Dict[str, Any]]:
    """Crawl URLs using basic HTTP fetch with httpx or urllib."""
    results = []
    
    for url in urls:
        try:
            # Try httpx first
            try:
                import httpx
                with httpx.Client(follow_redirects=True, timeout=30.0) as client:
                    response = client.get(url)
                    response.raise_for_status()
                    content = response.text
            except ImportError:
                # Fallback to urllib
                import urllib.request
                with urllib.request.urlopen(url, timeout=30) as response:
                    content = response.read().decode('utf-8', errors='ignore')
            
            # Basic HTML to text extraction
            import re
            # Remove script and style elements
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            content = re.sub(r'<[^>]+>', ' ', content)
            # Clean up whitespace
            content = re.sub(r'\s+', ' ', content).strip()
            
            # Extract title
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', content, re.IGNORECASE)
            title = title_match.group(1) if title_match else ""
            
            results.append({
                "url": url,
                "content": content[:50000],  # Limit content size
                "title": title,
                "provider": "httpx",
            })
        except Exception as e:
            results.append({
                "url": url,
                "content": "",
                "error": str(e),
                "provider": "httpx",
            })
    
    return results


def web_crawl(
    urls: Union[str, List[str]],
    provider: Optional[str] = None,
) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Crawl web pages and extract content.
    
    Auto-detects the best available provider based on installed packages and API keys.
    
    Provider priority:
    1. Tavily Extract (TAVILY_API_KEY) - highest quality
    2. Crawl4AI (no API key needed)
    3. Basic HTTP fetch (fallback)
    
    Args:
        urls: Single URL or list of URLs to crawl
        provider: Optional specific provider to use ('tavily', 'crawl4ai', 'httpx')
        
    Returns:
        Dict or list of dicts with keys: url, content, title, provider, error (if any)
    """
    # Normalize to list
    single_url = isinstance(urls, str)
    url_list = [urls] if single_url else urls
    
    # Get available providers
    available = _get_available_crawl_providers()
    
    if not available:
        return {"error": "No crawl providers available"}
    
    # Use specified provider or first available
    if provider and provider in available:
        selected = provider
    else:
        selected = available[0]
    
    logger.debug(f"Using crawl provider: {selected} (available: {available})")
    
    # Crawl with selected provider
    if selected == "tavily":
        results = _crawl_with_tavily(url_list)
    elif selected == "crawl4ai":
        results = _crawl_with_crawl4ai(url_list)
    else:
        results = _crawl_with_httpx(url_list)
    
    return results[0] if single_url else results


# Alias for consistency with search_web naming
crawl_web = web_crawl


def get_available_crawl_providers() -> List[str]:
    """Get list of available crawl providers."""
    return _get_available_crawl_providers()
