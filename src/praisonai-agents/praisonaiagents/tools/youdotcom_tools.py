"""You.com search and content tools.

You.com provides AI-powered web search, news search, content extraction, and image search.
This module requires the YDC_API_KEY environment variable to be set.

Usage:
    from praisonaiagents.tools import ydc_search, ydc_news, ydc_contents
    
    # Search the web (unified web + news)
    results = ydc_search("AI news 2024")
    
    # Get live news
    news = ydc_news("technology trends")
    
    # Extract content from URLs
    content = ydc_contents(["https://example.com"])
    
    # Or use the class directly
    from praisonaiagents.tools import YouTools
    you = YouTools()
    results = you.search("AI news")
"""

from typing import List, Dict, Any, Optional, Union
import logging
import os
from importlib import util


def _check_youdotcom_available() -> tuple[bool, Optional[str]]:
    """Check if You.com SDK is available and API key is set.
    
    Returns:
        Tuple of (is_available, error_message)
    """
    # Check if youdotcom package is installed
    if util.find_spec("youdotcom") is None:
        return False, "youdotcom package is not installed. Please install it using: pip install youdotcom"
    
    # Check if API key is set
    api_key = os.environ.get("YDC_API_KEY")
    if not api_key:
        return False, "YDC_API_KEY environment variable is not set. Please set it to use You.com tools."
    
    return True, None


class YouTools:
    """Comprehensive tools for web search and content using You.com API.
    
    You.com provides AI-powered search capabilities optimized for LLM applications.
    
    Features:
    - Unified web and news search with LLM-ready snippets
    - Live news search from authoritative sources
    - Content extraction from URLs (HTML/Markdown)
    - Image search
    - Advanced search operators support
    - Geographic and language targeting
    - Freshness controls
    
    Requires:
    - youdotcom package: pip install youdotcom
    - YDC_API_KEY environment variable
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize YouTools.
        
        Args:
            api_key: Optional API key. If not provided, uses YDC_API_KEY env var.
        """
        self._api_key = api_key
        self._client = None
    
    def _get_api_key(self) -> Optional[str]:
        """Get API key from instance or environment."""
        return self._api_key or os.environ.get("YDC_API_KEY")
    
    def _get_client(self):
        """Get or create You.com client."""
        if self._client is None:
            is_available, error = _check_youdotcom_available()
            if not is_available:
                return None, error
            
            from youdotcom import You
            api_key = self._get_api_key()
            if not api_key:
                return None, "YDC_API_KEY not set"
            self._client = You(api_key_auth=api_key)
        return self._client, None
    
    def search(
        self,
        query: str,
        count: int = 10,
        freshness: Optional[str] = None,
        country: Optional[str] = None,
        language: Optional[str] = None,
        offset: int = 0,
        safesearch: str = "moderate",
        livecrawl: Optional[str] = None,
        livecrawl_formats: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search the web using You.com's unified search API.
        
        Returns both web and news results in a single call with LLM-ready snippets.
        
        Args:
            query: Search query (supports operators like site:, filetype:, +term, -term)
            count: Max results per section (default 10, max 100)
            freshness: Filter by recency - "day", "week", "month", "year" or "YYYY-MM-DDtoYYYY-MM-DD"
            country: ISO country code (e.g., "US", "GB", "FR")
            language: BCP 47 language code (e.g., "EN", "JP", "DE")
            offset: Pagination offset (0-9), results = offset * count
            safesearch: Content filter - "off", "moderate", "strict"
            livecrawl: Fetch full content - "web", "news", or "all"
            livecrawl_formats: Content format - "html" or "markdown"
            
        Returns:
            Dict containing:
            - results: {web: [...], news: [...]}
            - metadata: {query, search_uuid, latency}
            
        Search Operators:
            - site:domain.com - Search within specific domain
            - filetype:pdf - Filter by file type
            - +term - Must include term
            - -term - Exclude term
            - AND, OR, NOT - Boolean operators
        """
        client, error = self._get_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            kwargs = {"query": query, "count": count, "offset": offset}
            
            if freshness:
                kwargs["freshness"] = freshness
            if country:
                kwargs["country"] = country
            if language:
                kwargs["language"] = language
            if safesearch:
                kwargs["safesearch"] = safesearch
            if livecrawl:
                kwargs["livecrawl"] = livecrawl
            if livecrawl_formats:
                kwargs["livecrawl_formats"] = livecrawl_formats
            
            response = client.search.unified(**kwargs)
            
            # Convert response to dict if it's a model object
            if hasattr(response, 'model_dump'):
                return response.model_dump()
            elif hasattr(response, 'to_dict'):
                return response.to_dict()
            elif hasattr(response, '__dict__'):
                return self._convert_response(response)
            return response
            
        except Exception as e:
            error_msg = f"You.com search error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    def _convert_response(self, response) -> Dict[str, Any]:
        """Convert SDK response object to dictionary."""
        result = {}
        
        if hasattr(response, 'results'):
            results = response.results
            result['results'] = {}
            if hasattr(results, 'web') and results.web:
                result['results']['web'] = [
                    {
                        'url': getattr(r, 'url', ''),
                        'title': getattr(r, 'title', ''),
                        'description': getattr(r, 'description', ''),
                        'snippets': getattr(r, 'snippets', []),
                        'thumbnail_url': getattr(r, 'thumbnail_url', None),
                        'page_age': getattr(r, 'page_age', None),
                        'favicon_url': getattr(r, 'favicon_url', None),
                        'authors': getattr(r, 'authors', []),
                    }
                    for r in results.web
                ]
            if hasattr(results, 'news') and results.news:
                result['results']['news'] = [
                    {
                        'url': getattr(r, 'url', ''),
                        'title': getattr(r, 'title', ''),
                        'description': getattr(r, 'description', ''),
                        'thumbnail_url': getattr(r, 'thumbnail_url', None),
                        'page_age': getattr(r, 'page_age', None),
                    }
                    for r in results.news
                ]
        
        if hasattr(response, 'metadata'):
            meta = response.metadata
            result['metadata'] = {
                'query': getattr(meta, 'query', ''),
                'search_uuid': getattr(meta, 'search_uuid', ''),
                'latency': getattr(meta, 'latency', 0),
            }
        
        return result
    
    def get_contents(
        self,
        urls: Union[str, List[str]],
        format: str = "markdown",
    ) -> Dict[str, Any]:
        """Fetch content from URLs using You.com's content extraction API.
        
        Args:
            urls: Single URL or list of URLs to fetch content from
            format: Content format - "html" or "markdown" (default: markdown)
            
        Returns:
            Dict containing array of results with:
            - url: The fetched URL
            - title: Page title
            - html: HTML content (if format="html")
            - markdown: Markdown content (if format="markdown")
            - metadata: {site_name, favicon_url}
        """
        client, error = self._get_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            if isinstance(urls, str):
                urls = [urls]
            
            # Use the contents endpoint
            response = client.search.contents(urls=urls, format=format)
            
            # Convert response
            if hasattr(response, 'model_dump'):
                return {"results": response.model_dump()}
            elif isinstance(response, list):
                return {"results": [
                    {
                        'url': getattr(r, 'url', ''),
                        'title': getattr(r, 'title', ''),
                        'html': getattr(r, 'html', None),
                        'markdown': getattr(r, 'markdown', None),
                        'metadata': {
                            'site_name': getattr(getattr(r, 'metadata', None), 'site_name', None) if hasattr(r, 'metadata') else None,
                            'favicon_url': getattr(getattr(r, 'metadata', None), 'favicon_url', None) if hasattr(r, 'metadata') else None,
                        }
                    }
                    for r in response
                ]}
            return {"results": response}
            
        except Exception as e:
            error_msg = f"You.com contents error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    def live_news(
        self,
        query: str,
        count: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Search for live news using You.com's news API.
        
        Note: This API may require early access. Contact api@you.com for access.
        
        Args:
            query: News search query
            count: Maximum number of news results to return
            
        Returns:
            Dict containing:
            - news: {query, results: [...], metadata}
            - Each result has: title, description, url, page_age, source_name, thumbnail
        """
        client, error = self._get_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            kwargs = {"q": query}
            if count:
                kwargs["count"] = count
            
            # Try to access live news endpoint
            if hasattr(client, 'livenews'):
                response = client.livenews.get(**kwargs)
            else:
                # Fallback: use unified search with news focus
                return self.search(query=query, count=count or 10)
            
            if hasattr(response, 'model_dump'):
                return response.model_dump()
            elif hasattr(response, 'news'):
                news = response.news
                return {
                    'news': {
                        'query': getattr(getattr(news, 'query', None), 'original', query) if hasattr(news, 'query') else query,
                        'results': [
                            {
                                'title': getattr(r, 'title', ''),
                                'description': getattr(r, 'description', ''),
                                'url': getattr(r, 'url', ''),
                                'page_age': getattr(r, 'page_age', None),
                                'age': getattr(r, 'age', None),
                                'source_name': getattr(r, 'source_name', None),
                                'thumbnail': getattr(getattr(r, 'thumbnail', None), 'src', None) if hasattr(r, 'thumbnail') else None,
                            }
                            for r in getattr(news, 'results', [])
                        ],
                        'metadata': {
                            'request_uuid': getattr(getattr(news, 'metadata', None), 'request_uuid', None) if hasattr(news, 'metadata') else None,
                        }
                    }
                }
            return response
            
        except Exception as e:
            error_msg = f"You.com live news error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    def images(
        self,
        query: str,
    ) -> Dict[str, Any]:
        """Search for images using You.com's image search API.
        
        Note: This API may require early access. Contact api@you.com for access.
        
        Args:
            query: Image search query
            
        Returns:
            Dict containing:
            - images: {results: [...]}
            - metadata: {query, search_uuid}
            - Each result has: title, page_url, image_url
        """
        client, error = self._get_client()
        if error:
            logging.error(error)
            return {"error": error}
        
        try:
            if hasattr(client, 'images'):
                response = client.images.get(q=query)
            else:
                return {"error": "Image search not available in this SDK version"}
            
            if hasattr(response, 'model_dump'):
                return response.model_dump()
            elif hasattr(response, 'images'):
                images = response.images
                return {
                    'images': {
                        'results': [
                            {
                                'title': getattr(r, 'title', ''),
                                'page_url': getattr(r, 'page_url', ''),
                                'image_url': getattr(r, 'image_url', ''),
                            }
                            for r in getattr(images, 'results', [])
                        ]
                    },
                    'metadata': {
                        'query': getattr(getattr(response, 'metadata', None), 'query', query) if hasattr(response, 'metadata') else query,
                        'search_uuid': getattr(getattr(response, 'metadata', None), 'search_uuid', None) if hasattr(response, 'metadata') else None,
                    }
                }
            return response
            
        except Exception as e:
            error_msg = f"You.com images error: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self._client is not None:
            # Close client if it has a close method
            if hasattr(self._client, 'close'):
                self._client.close()
            elif hasattr(self._client, '__exit__'):
                self._client.__exit__(exc_type, exc_val, exc_tb)
        return False


# Standalone functions for direct import
def ydc_search(
    query: str,
    count: int = 10,
    freshness: Optional[str] = None,
    country: Optional[str] = None,
    language: Optional[str] = None,
    offset: int = 0,
    safesearch: str = "moderate",
    livecrawl: Optional[str] = None,
    livecrawl_formats: Optional[str] = None,
) -> Dict[str, Any]:
    """Search the web using You.com's unified search API.
    
    This is a convenience function that creates a YouTools instance.
    For repeated calls, consider using YouTools class directly.
    
    Args:
        query: Search query (supports operators like site:, filetype:, +term, -term)
        count: Max results per section (default 10, max 100)
        freshness: Filter by recency - "day", "week", "month", "year"
        country: ISO country code (e.g., "US", "GB")
        language: BCP 47 language code (e.g., "EN", "JP")
        offset: Pagination offset (0-9)
        safesearch: Content filter - "off", "moderate", "strict"
        livecrawl: Fetch full content - "web", "news", or "all"
        livecrawl_formats: Content format - "html" or "markdown"
        
    Returns:
        Dict containing search results with web and news sections
    """
    tools = YouTools()
    return tools.search(
        query=query,
        count=count,
        freshness=freshness,
        country=country,
        language=language,
        offset=offset,
        safesearch=safesearch,
        livecrawl=livecrawl,
        livecrawl_formats=livecrawl_formats,
    )


def ydc_contents(
    urls: Union[str, List[str]],
    format: str = "markdown",
) -> Dict[str, Any]:
    """Fetch content from URLs using You.com's content extraction API.
    
    Args:
        urls: Single URL or list of URLs to fetch content from
        format: Content format - "html" or "markdown"
        
    Returns:
        Dict containing extracted content for each URL
    """
    tools = YouTools()
    return tools.get_contents(urls=urls, format=format)


def ydc_news(
    query: str,
    count: Optional[int] = None,
) -> Dict[str, Any]:
    """Search for live news using You.com's news API.
    
    Args:
        query: News search query
        count: Maximum number of results
        
    Returns:
        Dict containing news results
    """
    tools = YouTools()
    return tools.live_news(query=query, count=count)


def ydc_images(
    query: str,
) -> Dict[str, Any]:
    """Search for images using You.com's image search API.
    
    Args:
        query: Image search query
        
    Returns:
        Dict containing image results
    """
    tools = YouTools()
    return tools.images(query=query)


if __name__ == "__main__":
    # Example usage
    print("\n" + "=" * 60)
    print("You.com Tools Demonstration")
    print("=" * 60 + "\n")
    
    # Check if API key is available
    is_available, error = _check_youdotcom_available()
    if not is_available:
        print(f"Error: {error}")
        print("\nTo use You.com tools:")
        print("1. Install: pip install youdotcom")
        print("2. Set environment variable: export YDC_API_KEY=your_api_key")
    else:
        print("You.com SDK is available!")
        
        # Example search
        print("\n1. Basic Search")
        print("-" * 30)
        results = ydc_search("Latest AI developments 2024", count=3)
        if "error" not in results:
            web_results = results.get('results', {}).get('web', [])
            print(f"Found {len(web_results)} web results")
            for r in web_results[:3]:
                print(f"  - {r.get('title', 'No title')[:50]}...")
                print(f"    URL: {r.get('url', 'No URL')}")
        else:
            print(f"Error: {results['error']}")
        
        print("\n" + "=" * 60)
        print("Demonstration Complete")
        print("=" * 60)


# Alias for simple usage: from praisonaiagents.tools import ydc
ydc = ydc_search
