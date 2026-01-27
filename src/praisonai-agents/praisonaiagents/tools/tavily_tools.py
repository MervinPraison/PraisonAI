"""Tavily search and extraction tools.

Tavily provides AI-powered web search, content extraction, and crawling capabilities.
This module requires the TAVILY_API_KEY environment variable to be set.

Usage:
    from praisonaiagents.tools import tavily_search, tavily_extract
    
    # Search the web
    results = tavily_search("AI news 2024")
    
    # Extract content from URLs
    content = tavily_extract("https://example.com")
    
    # Or use the class directly
    from praisonaiagents.tools import TavilyTools
    tavily = TavilyTools()
    results = tavily.search("AI news")
"""

from typing import List, Dict, Any, Optional, Union
import logging
import os
from importlib import util


def _check_tavily_available() -> tuple[bool, Optional[str]]:
    """Check if Tavily is available and API key is set.
    
    Returns:
        Tuple of (is_available, error_message)
    """
    # Check if tavily package is installed
    if util.find_spec("tavily") is None:
        return False, "Tavily package is not installed. Please install it using: pip install tavily-python"
    
    # Check if API key is set
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return False, "TAVILY_API_KEY environment variable is not set. Please set it to use Tavily tools."
    
    return True, None


class TavilyTools:
    """Comprehensive tools for web search and content extraction using Tavily API.
    
    Tavily provides AI-powered search capabilities optimized for LLM applications.
    
    Features:
    - Web search with advanced filtering and ranking
    - Content extraction from URLs
    - Website crawling with intelligent navigation
    - Site mapping
    
    Requires:
    - tavily-python package: pip install tavily-python
    - TAVILY_API_KEY environment variable
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize TavilyTools.
        
        Args:
            api_key: Optional API key. If not provided, uses TAVILY_API_KEY env var.
        """
        self._api_key = api_key
        self._client = None
        self._async_client = None
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from instance or environment."""
        return self._api_key or os.environ.get("TAVILY_API_KEY")
    
    def _get_client(self):
        """Get or create synchronous Tavily client."""
        if self._client is None:
            is_available, error = _check_tavily_available()
            if not is_available:
                return None, error
            
            from tavily import TavilyClient
            api_key = self._get_api_key()
            if not api_key:
                return None, "TAVILY_API_KEY not set"
            self._client = TavilyClient(api_key=api_key)
        return self._client, None
    
    def _get_async_client(self):
        """Get or create asynchronous Tavily client."""
        if self._async_client is None:
            is_available, error = _check_tavily_available()
            if not is_available:
                return None, error
            
            from tavily import AsyncTavilyClient
            api_key = self._get_api_key()
            if not api_key:
                return None, "TAVILY_API_KEY not set"
            self._async_client = AsyncTavilyClient(api_key=api_key)
        return self._async_client, None
    
    def search(
        self,
        query: str,
        search_depth: str = "basic",
        topic: str = "general",
        max_results: int = 5,
        include_answer: bool = False,
        include_raw_content: bool = False,
        include_images: bool = False,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        time_range: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search the web using Tavily's AI-powered search.
        
        Args:
            query: The search query
            search_depth: "basic" or "advanced" (advanced uses more credits but better results)
            topic: "general", "news", or "finance"
            max_results: Maximum number of results (1-20)
            include_answer: Include LLM-generated answer based on results
            include_raw_content: Include cleaned HTML content of each result
            include_images: Include query-related images
            include_domains: List of domains to include (max 300)
            exclude_domains: List of domains to exclude (max 150)
            time_range: Filter by time - "day", "week", "month", "year" or "d", "w", "m", "y"
            
        Returns:
            Dict containing search results with keys:
            - results: List of search results with title, url, content, score
            - query: The search query
            - response_time: Time taken for search
            - answer: (optional) LLM-generated answer if include_answer=True
            - images: (optional) List of image URLs if include_images=True
        """
        client, error = self._get_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            kwargs = {
                "query": query,
                "search_depth": search_depth,
                "topic": topic,
                "max_results": max_results,
                "include_answer": include_answer,
                "include_raw_content": include_raw_content,
                "include_images": include_images,
            }
            
            if include_domains:
                kwargs["include_domains"] = include_domains
            if exclude_domains:
                kwargs["exclude_domains"] = exclude_domains
            if time_range:
                kwargs["time_range"] = time_range
            
            response = client.search(**kwargs)
            return response
            
        except Exception as e:
            error_msg = f"Tavily search error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    def extract(
        self,
        urls: Union[str, List[str]],
        include_images: bool = False,
        extract_depth: str = "basic",
    ) -> Dict[str, Any]:
        """Extract content from one or more URLs.
        
        Args:
            urls: Single URL or list of URLs (max 20)
            include_images: Include extracted images
            extract_depth: "basic" or "advanced" (advanced retrieves more data)
            
        Returns:
            Dict containing:
            - results: List of successful extractions with url, raw_content
            - failed_results: List of URLs that failed with error messages
            - response_time: Time taken for extraction
        """
        client, error = self._get_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            response = client.extract(
                urls=urls,
                include_images=include_images,
                extract_depth=extract_depth,
            )
            return response
            
        except Exception as e:
            error_msg = f"Tavily extract error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    def crawl(
        self,
        url: str,
        max_depth: int = 1,
        max_breadth: int = 20,
        limit: int = 50,
        instructions: Optional[str] = None,
        include_images: bool = False,
        extract_depth: str = "basic",
    ) -> Dict[str, Any]:
        """Crawl a website starting from a base URL.
        
        Args:
            url: The root URL to begin crawling
            max_depth: Maximum depth from base URL (default: 1)
            max_breadth: Max links to follow per page (default: 20)
            limit: Total links to process before stopping (default: 50)
            instructions: Natural language instructions for the crawler
            include_images: Extract image URLs from pages
            extract_depth: "basic" or "advanced"
            
        Returns:
            Dict containing:
            - base_url: The starting URL
            - results: List of crawled pages with url, raw_content, images
            - response_time: Time taken for crawl
        """
        client, error = self._get_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            kwargs = {
                "url": url,
                "max_depth": max_depth,
                "max_breadth": max_breadth,
                "limit": limit,
                "include_images": include_images,
                "extract_depth": extract_depth,
            }
            
            if instructions:
                kwargs["instructions"] = instructions
            
            response = client.crawl(**kwargs)
            return response
            
        except Exception as e:
            error_msg = f"Tavily crawl error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    def map(
        self,
        url: str,
        max_depth: int = 1,
        max_breadth: int = 20,
        limit: int = 50,
        instructions: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get a sitemap starting from a base URL.
        
        Args:
            url: The root URL to begin mapping
            max_depth: Maximum depth from base URL (default: 1)
            max_breadth: Max links to follow per page (default: 20)
            limit: Total links to process before stopping (default: 50)
            instructions: Natural language instructions for the mapper
            
        Returns:
            Dict containing:
            - base_url: The starting URL
            - results: List of discovered URLs
            - response_time: Time taken for mapping
        """
        client, error = self._get_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            kwargs = {
                "url": url,
                "max_depth": max_depth,
                "max_breadth": max_breadth,
                "limit": limit,
            }
            
            if instructions:
                kwargs["instructions"] = instructions
            
            response = client.map(**kwargs)
            return response
            
        except Exception as e:
            error_msg = f"Tavily map error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    # Async methods
    async def asearch(
        self,
        query: str,
        search_depth: str = "basic",
        topic: str = "general",
        max_results: int = 5,
        include_answer: bool = False,
        include_raw_content: bool = False,
        include_images: bool = False,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        time_range: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Async version of search. See search() for documentation."""
        client, error = self._get_async_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            kwargs = {
                "query": query,
                "search_depth": search_depth,
                "topic": topic,
                "max_results": max_results,
                "include_answer": include_answer,
                "include_raw_content": include_raw_content,
                "include_images": include_images,
            }
            
            if include_domains:
                kwargs["include_domains"] = include_domains
            if exclude_domains:
                kwargs["exclude_domains"] = exclude_domains
            if time_range:
                kwargs["time_range"] = time_range
            
            response = await client.search(**kwargs)
            return response
            
        except Exception as e:
            error_msg = f"Tavily async search error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    async def aextract(
        self,
        urls: Union[str, List[str]],
        include_images: bool = False,
        extract_depth: str = "basic",
    ) -> Dict[str, Any]:
        """Async version of extract. See extract() for documentation."""
        client, error = self._get_async_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            response = await client.extract(
                urls=urls,
                include_images=include_images,
                extract_depth=extract_depth,
            )
            return response
            
        except Exception as e:
            error_msg = f"Tavily async extract error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}


# Standalone functions for direct import

def tavily_search(
    query: str,
    search_depth: str = "basic",
    topic: str = "general",
    max_results: int = 5,
    include_answer: bool = False,
    include_raw_content: bool = True,
    include_images: bool = False,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    time_range: Optional[str] = None,
) -> Dict[str, Any]:
    """Search the web using Tavily's AI-powered search.
    
    This is a convenience function that creates a TavilyTools instance.
    For repeated calls, consider using TavilyTools class directly.
    
    Args:
        query: The search query
        search_depth: "basic" or "advanced"
        topic: "general", "news", or "finance"
        max_results: Maximum number of results (1-20), default 5
        include_answer: Include LLM-generated answer
        include_raw_content: Include cleaned HTML content (default True for research quality)
        include_images: Include query-related images
        include_domains: List of domains to include
        exclude_domains: List of domains to exclude
        time_range: Filter by time - "day", "week", "month", "year"
        
    Returns:
        Dict containing search results with full raw content by default
    """
    tools = TavilyTools()
    return tools.search(
        query=query,
        search_depth=search_depth,
        topic=topic,
        max_results=max_results,
        include_answer=include_answer,
        include_raw_content=include_raw_content,
        include_images=include_images,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        time_range=time_range,
    )


def tavily_extract(
    urls: Union[str, List[str]],
    include_images: bool = False,
    extract_depth: str = "basic",
) -> Dict[str, Any]:
    """Extract content from one or more URLs using Tavily.
    
    Args:
        urls: Single URL or list of URLs (max 20)
        include_images: Include extracted images
        extract_depth: "basic" or "advanced"
        
    Returns:
        Dict containing extraction results
    """
    tools = TavilyTools()
    return tools.extract(
        urls=urls,
        include_images=include_images,
        extract_depth=extract_depth,
    )


def tavily_crawl(
    url: str,
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 50,
    instructions: Optional[str] = None,
    include_images: bool = False,
    extract_depth: str = "basic",
) -> Dict[str, Any]:
    """Crawl a website starting from a base URL using Tavily.
    
    Args:
        url: The root URL to begin crawling
        max_depth: Maximum depth from base URL
        max_breadth: Max links to follow per page
        limit: Total links to process before stopping
        instructions: Natural language instructions for the crawler
        include_images: Extract image URLs from pages
        extract_depth: "basic" or "advanced"
        
    Returns:
        Dict containing crawl results
    """
    tools = TavilyTools()
    return tools.crawl(
        url=url,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
        instructions=instructions,
        include_images=include_images,
        extract_depth=extract_depth,
    )


def tavily_map(
    url: str,
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 50,
    instructions: Optional[str] = None,
) -> Dict[str, Any]:
    """Get a sitemap starting from a base URL using Tavily.
    
    Args:
        url: The root URL to begin mapping
        max_depth: Maximum depth from base URL
        max_breadth: Max links to follow per page
        limit: Total links to process before stopping
        instructions: Natural language instructions for the mapper
        
    Returns:
        Dict containing map results with discovered URLs
    """
    tools = TavilyTools()
    return tools.map(
        url=url,
        max_depth=max_depth,
        max_breadth=max_breadth,
        limit=limit,
        instructions=instructions,
    )


# Async standalone functions
async def tavily_search_async(
    query: str,
    search_depth: str = "basic",
    topic: str = "general",
    max_results: int = 5,
    include_answer: bool = False,
    include_raw_content: bool = False,
    include_images: bool = False,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    time_range: Optional[str] = None,
) -> Dict[str, Any]:
    """Async version of tavily_search. See tavily_search() for documentation."""
    tools = TavilyTools()
    return await tools.asearch(
        query=query,
        search_depth=search_depth,
        topic=topic,
        max_results=max_results,
        include_answer=include_answer,
        include_raw_content=include_raw_content,
        include_images=include_images,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        time_range=time_range,
    )


async def tavily_extract_async(
    urls: Union[str, List[str]],
    include_images: bool = False,
    extract_depth: str = "basic",
) -> Dict[str, Any]:
    """Async version of tavily_extract. See tavily_extract() for documentation."""
    tools = TavilyTools()
    return await tools.aextract(
        urls=urls,
        include_images=include_images,
        extract_depth=extract_depth,
    )


if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("Tavily Tools Demonstration")
    print("==================================================\n")
    
    # Check if API key is available
    is_available, error = _check_tavily_available()
    if not is_available:
        print(f"Error: {error}")
        print("\nTo use Tavily tools:")
        print("1. Install: pip install tavily-python")
        print("2. Set environment variable: export TAVILY_API_KEY=your_api_key")
    else:
        print("Tavily is available!")
        
        # Example search
        print("\n1. Basic Search")
        print("-" * 30)
        results = tavily_search("Latest AI developments 2024", max_results=3)
        if "error" not in results:
            print(f"Found {len(results.get('results', []))} results")
            for r in results.get("results", [])[:3]:
                print(f"  - {r.get('title', 'No title')}")
                print(f"    URL: {r.get('url', 'No URL')}")
        else:
            print(f"Error: {results['error']}")
        
        print("\n==================================================")
        print("Demonstration Complete")
        print("==================================================")


# Alias for simple usage: from praisonaiagents.tools import tavily
tavily = tavily_search
