"""Exa search and research tools.

Exa provides AI-powered web search, content retrieval, and research capabilities.
This module requires the EXA_API_KEY environment variable to be set.

Usage:
    from praisonaiagents.tools import exa_search, exa_search_contents
    
    # Search the web
    results = exa_search("AI startups")
    
    # Search with contents
    results = exa_search_contents("AI in healthcare", text=True)
    
    # Or use the class directly
    from praisonaiagents.tools import ExaTools
    exa = ExaTools()
    results = exa.search("AI news")
"""

from typing import List, Dict, Any, Optional, Union
import logging
import os
from importlib import util


def _check_exa_available() -> tuple[bool, Optional[str]]:
    """Check if Exa is available and API key is set.
    
    Returns:
        Tuple of (is_available, error_message)
    """
    # Check if exa_py package is installed
    if util.find_spec("exa_py") is None:
        return False, "exa_py package is not installed. Install it with: pip install exa_py"
    
    # Check if API key is set
    if not os.environ.get("EXA_API_KEY"):
        return False, "EXA_API_KEY environment variable is not set. Please set it to use Exa tools."
    
    return True, None


class ExaTools:
    """Exa search and research tools.
    
    Provides methods for:
    - search: Basic web search
    - search_and_contents: Search with full text/highlights
    - find_similar: Find similar pages to a URL
    - find_similar_and_contents: Find similar with content
    - answer: Get AI-generated answers with citations
    
    Example:
        from praisonaiagents.tools import ExaTools
        
        exa = ExaTools()
        results = exa.search("AI startups", num_results=5)
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize ExaTools.
        
        Args:
            api_key: Exa API key. If not provided, uses EXA_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("EXA_API_KEY")
        self._client = None
        self.logger = logging.getLogger(__name__)
    
    def _get_client(self):
        """Get or create Exa client."""
        if self._client is None:
            is_available, error = _check_exa_available()
            if not is_available:
                raise ImportError(error)
            
            from exa_py import Exa
            self._client = Exa(self.api_key)
        return self._client
    
    def search(
        self,
        query: str,
        num_results: int = 10,
        type: Optional[str] = None,
        category: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        start_crawl_date: Optional[str] = None,
        end_crawl_date: Optional[str] = None,
        start_published_date: Optional[str] = None,
        end_published_date: Optional[str] = None,
        include_text: Optional[List[str]] = None,
        exclude_text: Optional[List[str]] = None,
        additional_queries: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Perform an Exa search.
        
        Args:
            query: The search query
            num_results: Number of results to return (default 10, max 100)
            type: Search type - "auto", "neural", "fast", or "deep"
            category: Data category - company, research paper, news, linkedin profile, 
                     github, tweet, movie, song, personal site, pdf, financial report
            include_domains: List of domains to include
            exclude_domains: List of domains to exclude
            start_crawl_date: Only include links crawled after this date
            end_crawl_date: Only include links crawled before this date
            start_published_date: Only include links published after this date
            end_published_date: Only include links published before this date
            include_text: Strings that must be present in results
            exclude_text: Strings that must not be present in results
            additional_queries: Additional query variations for deep search
            
        Returns:
            Dict with 'results' list and optional 'autopromptString'
        """
        try:
            client = self._get_client()
            
            kwargs = {
                "query": query,
                "num_results": num_results
            }
            
            if type:
                kwargs["type"] = type
            if category:
                kwargs["category"] = category
            if include_domains:
                kwargs["include_domains"] = include_domains
            if exclude_domains:
                kwargs["exclude_domains"] = exclude_domains
            if start_crawl_date:
                kwargs["start_crawl_date"] = start_crawl_date
            if end_crawl_date:
                kwargs["end_crawl_date"] = end_crawl_date
            if start_published_date:
                kwargs["start_published_date"] = start_published_date
            if end_published_date:
                kwargs["end_published_date"] = end_published_date
            if include_text:
                kwargs["include_text"] = include_text
            if exclude_text:
                kwargs["exclude_text"] = exclude_text
            if additional_queries:
                kwargs["additional_queries"] = additional_queries
            
            response = client.search(**kwargs)
            
            return {
                "results": [
                    {
                        "url": r.url,
                        "id": r.id,
                        "title": getattr(r, "title", None),
                        "published_date": getattr(r, "published_date", None),
                        "author": getattr(r, "author", None)
                    }
                    for r in response.results
                ],
                "autopromptString": getattr(response, "autoprompt_string", None),
                "requestId": getattr(response, "request_id", None)
            }
            
        except Exception as e:
            self.logger.error(f"Exa search error: {e}")
            return {"error": f"Exa search error: {str(e)}"}
    
    def search_and_contents(
        self,
        query: str,
        text: Union[bool, Dict] = True,
        highlights: Union[bool, Dict] = False,
        summary: Optional[Dict] = None,
        num_results: int = 10,
        type: Optional[str] = None,
        category: Optional[str] = None,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        start_crawl_date: Optional[str] = None,
        end_crawl_date: Optional[str] = None,
        start_published_date: Optional[str] = None,
        end_published_date: Optional[str] = None,
        include_text: Optional[List[str]] = None,
        exclude_text: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Search and retrieve content from results.
        
        Args:
            query: The search query
            text: Include full text content (True or TextContentsOptions dict)
            highlights: Include highlights (True or HighlightsContentsOptions dict)
            summary: Summary options with optional schema for structured output
            num_results: Number of results to return
            type: Search type - "auto", "neural", "fast", or "deep"
            category: Data category filter
            include_domains: List of domains to include
            exclude_domains: List of domains to exclude
            start_crawl_date: Only include links crawled after this date
            end_crawl_date: Only include links crawled before this date
            start_published_date: Only include links published after this date
            end_published_date: Only include links published before this date
            include_text: Strings that must be present in results
            exclude_text: Strings that must not be present in results
            
        Returns:
            Dict with 'results' list containing text/highlights
        """
        try:
            client = self._get_client()
            
            kwargs = {
                "query": query,
                "num_results": num_results
            }
            
            if text:
                kwargs["text"] = text
            if highlights:
                kwargs["highlights"] = highlights
            if summary:
                kwargs["summary"] = summary
            if type:
                kwargs["type"] = type
            if category:
                kwargs["category"] = category
            if include_domains:
                kwargs["include_domains"] = include_domains
            if exclude_domains:
                kwargs["exclude_domains"] = exclude_domains
            if start_crawl_date:
                kwargs["start_crawl_date"] = start_crawl_date
            if end_crawl_date:
                kwargs["end_crawl_date"] = end_crawl_date
            if start_published_date:
                kwargs["start_published_date"] = start_published_date
            if end_published_date:
                kwargs["end_published_date"] = end_published_date
            if include_text:
                kwargs["include_text"] = include_text
            if exclude_text:
                kwargs["exclude_text"] = exclude_text
            
            response = client.search_and_contents(**kwargs)
            
            results = []
            for r in response.results:
                result = {
                    "url": r.url,
                    "id": r.id,
                    "title": getattr(r, "title", None),
                    "published_date": getattr(r, "published_date", None),
                    "author": getattr(r, "author", None)
                }
                if hasattr(r, "text") and r.text:
                    result["text"] = r.text
                if hasattr(r, "highlights") and r.highlights:
                    result["highlights"] = r.highlights
                if hasattr(r, "highlight_scores") and r.highlight_scores:
                    result["highlight_scores"] = r.highlight_scores
                if hasattr(r, "summary") and r.summary:
                    result["summary"] = r.summary
                results.append(result)
            
            return {
                "results": results,
                "requestId": getattr(response, "request_id", None)
            }
            
        except Exception as e:
            self.logger.error(f"Exa search_and_contents error: {e}")
            return {"error": f"Exa search_and_contents error: {str(e)}"}
    
    def find_similar(
        self,
        url: str,
        num_results: int = 10,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        start_crawl_date: Optional[str] = None,
        end_crawl_date: Optional[str] = None,
        start_published_date: Optional[str] = None,
        end_published_date: Optional[str] = None,
        exclude_source_domain: bool = False,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find similar pages to a given URL.
        
        Args:
            url: The URL to find similar pages for
            num_results: Number of results to return
            include_domains: List of domains to include
            exclude_domains: List of domains to exclude
            start_crawl_date: Only include links crawled after this date
            end_crawl_date: Only include links crawled before this date
            start_published_date: Only include links published after this date
            end_published_date: Only include links published before this date
            exclude_source_domain: Exclude results from the same domain
            category: Data category filter
            
        Returns:
            Dict with 'results' list of similar pages
        """
        try:
            client = self._get_client()
            
            kwargs = {
                "url": url,
                "num_results": num_results
            }
            
            if include_domains:
                kwargs["include_domains"] = include_domains
            if exclude_domains:
                kwargs["exclude_domains"] = exclude_domains
            if start_crawl_date:
                kwargs["start_crawl_date"] = start_crawl_date
            if end_crawl_date:
                kwargs["end_crawl_date"] = end_crawl_date
            if start_published_date:
                kwargs["start_published_date"] = start_published_date
            if end_published_date:
                kwargs["end_published_date"] = end_published_date
            if exclude_source_domain:
                kwargs["exclude_source_domain"] = exclude_source_domain
            if category:
                kwargs["category"] = category
            
            response = client.find_similar(**kwargs)
            
            return {
                "results": [
                    {
                        "url": r.url,
                        "id": r.id,
                        "title": getattr(r, "title", None),
                        "published_date": getattr(r, "published_date", None),
                        "author": getattr(r, "author", None)
                    }
                    for r in response.results
                ],
                "requestId": getattr(response, "request_id", None)
            }
            
        except Exception as e:
            self.logger.error(f"Exa find_similar error: {e}")
            return {"error": f"Exa find_similar error: {str(e)}"}
    
    def find_similar_and_contents(
        self,
        url: str,
        text: Union[bool, Dict] = True,
        highlights: Union[bool, Dict] = False,
        num_results: int = 10,
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
        start_crawl_date: Optional[str] = None,
        end_crawl_date: Optional[str] = None,
        start_published_date: Optional[str] = None,
        end_published_date: Optional[str] = None,
        exclude_source_domain: bool = False,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """Find similar pages with content.
        
        Args:
            url: The URL to find similar pages for
            text: Include full text content
            highlights: Include highlights
            num_results: Number of results to return
            include_domains: List of domains to include
            exclude_domains: List of domains to exclude
            start_crawl_date: Only include links crawled after this date
            end_crawl_date: Only include links crawled before this date
            start_published_date: Only include links published after this date
            end_published_date: Only include links published before this date
            exclude_source_domain: Exclude results from the same domain
            category: Data category filter
            
        Returns:
            Dict with 'results' list containing text/highlights
        """
        try:
            client = self._get_client()
            
            kwargs = {
                "url": url,
                "num_results": num_results
            }
            
            if text:
                kwargs["text"] = text
            if highlights:
                kwargs["highlights"] = highlights
            if include_domains:
                kwargs["include_domains"] = include_domains
            if exclude_domains:
                kwargs["exclude_domains"] = exclude_domains
            if start_crawl_date:
                kwargs["start_crawl_date"] = start_crawl_date
            if end_crawl_date:
                kwargs["end_crawl_date"] = end_crawl_date
            if start_published_date:
                kwargs["start_published_date"] = start_published_date
            if end_published_date:
                kwargs["end_published_date"] = end_published_date
            if exclude_source_domain:
                kwargs["exclude_source_domain"] = exclude_source_domain
            if category:
                kwargs["category"] = category
            
            response = client.find_similar_and_contents(**kwargs)
            
            results = []
            for r in response.results:
                result = {
                    "url": r.url,
                    "id": r.id,
                    "title": getattr(r, "title", None),
                    "published_date": getattr(r, "published_date", None),
                    "author": getattr(r, "author", None)
                }
                if hasattr(r, "text") and r.text:
                    result["text"] = r.text
                if hasattr(r, "highlights") and r.highlights:
                    result["highlights"] = r.highlights
                if hasattr(r, "highlight_scores") and r.highlight_scores:
                    result["highlight_scores"] = r.highlight_scores
                results.append(result)
            
            return {
                "results": results,
                "requestId": getattr(response, "request_id", None)
            }
            
        except Exception as e:
            self.logger.error(f"Exa find_similar_and_contents error: {e}")
            return {"error": f"Exa find_similar_and_contents error: {str(e)}"}
    
    def answer(
        self,
        query: str,
        text: bool = False
    ) -> Dict[str, Any]:
        """Generate an answer using Exa's search and LLM capabilities.
        
        Args:
            query: The question to answer
            text: If True, include full text of citations
            
        Returns:
            Dict with 'answer' and 'citations'
        """
        try:
            client = self._get_client()
            
            response = client.answer(query=query, text=text)
            
            citations = []
            for c in response.citations:
                citation = {
                    "id": c.id,
                    "url": c.url,
                    "title": getattr(c, "title", None),
                    "published_date": getattr(c, "published_date", None),
                    "author": getattr(c, "author", None)
                }
                if text and hasattr(c, "text") and c.text:
                    citation["text"] = c.text
                citations.append(citation)
            
            return {
                "answer": response.answer,
                "citations": citations
            }
            
        except Exception as e:
            self.logger.error(f"Exa answer error: {e}")
            return {"error": f"Exa answer error: {str(e)}"}


# Standalone functions for easy access

def exa_search(
    query: str,
    num_results: int = 10,
    type: Optional[str] = None,
    category: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    start_published_date: Optional[str] = None,
    end_published_date: Optional[str] = None
) -> Dict[str, Any]:
    """Search the web using Exa.
    
    Args:
        query: The search query
        num_results: Number of results (default 10)
        type: Search type - "auto", "neural", "fast", or "deep"
        category: Data category filter
        include_domains: Domains to include
        exclude_domains: Domains to exclude
        start_published_date: Only include links published after this date
        end_published_date: Only include links published before this date
        
    Returns:
        Dict with search results or error
        
    Example:
        results = exa_search("AI startups", num_results=5)
    """
    is_available, error = _check_exa_available()
    if not is_available:
        logging.error(error)
        return {"error": error}
    
    tools = ExaTools()
    return tools.search(
        query=query,
        num_results=num_results,
        type=type,
        category=category,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        start_published_date=start_published_date,
        end_published_date=end_published_date
    )


def exa_search_contents(
    query: str,
    text: bool = True,
    highlights: bool = False,
    num_results: int = 10,
    type: Optional[str] = None,
    category: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Search and get content from results.
    
    Args:
        query: The search query
        text: Include full text content
        highlights: Include highlights
        num_results: Number of results
        type: Search type
        category: Data category filter
        include_domains: Domains to include
        exclude_domains: Domains to exclude
        
    Returns:
        Dict with results containing text/highlights
        
    Example:
        results = exa_search_contents("AI in healthcare", text=True, highlights=True)
    """
    is_available, error = _check_exa_available()
    if not is_available:
        logging.error(error)
        return {"error": error}
    
    tools = ExaTools()
    return tools.search_and_contents(
        query=query,
        text=text,
        highlights=highlights,
        num_results=num_results,
        type=type,
        category=category,
        include_domains=include_domains,
        exclude_domains=exclude_domains
    )


def exa_find_similar(
    url: str,
    num_results: int = 10,
    exclude_source_domain: bool = True,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """Find pages similar to a given URL.
    
    Args:
        url: The URL to find similar pages for
        num_results: Number of results
        exclude_source_domain: Exclude same domain results
        category: Data category filter
        
    Returns:
        Dict with similar results
        
    Example:
        results = exa_find_similar("https://openai.com", num_results=5)
    """
    is_available, error = _check_exa_available()
    if not is_available:
        logging.error(error)
        return {"error": error}
    
    tools = ExaTools()
    return tools.find_similar(
        url=url,
        num_results=num_results,
        exclude_source_domain=exclude_source_domain,
        category=category
    )


def exa_answer(
    query: str,
    text: bool = False
) -> Dict[str, Any]:
    """Get an AI-generated answer with citations.
    
    Args:
        query: The question to answer
        text: Include full text of citations
        
    Returns:
        Dict with 'answer' and 'citations'
        
    Example:
        result = exa_answer("What is the capital of France?")
        print(result["answer"])
    """
    is_available, error = _check_exa_available()
    if not is_available:
        logging.error(error)
        return {"error": error}
    
    tools = ExaTools()
    return tools.answer(query=query, text=text)


# Async versions

async def exa_search_async(
    query: str,
    num_results: int = 10,
    type: Optional[str] = None,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """Async version of exa_search.
    
    Args:
        query: The search query
        num_results: Number of results
        type: Search type
        category: Data category filter
        
    Returns:
        Dict with search results
    """
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: exa_search(query, num_results, type, category)
    )


async def exa_search_contents_async(
    query: str,
    text: bool = True,
    highlights: bool = False,
    num_results: int = 10
) -> Dict[str, Any]:
    """Async version of exa_search_contents.
    
    Args:
        query: The search query
        text: Include full text
        highlights: Include highlights
        num_results: Number of results
        
    Returns:
        Dict with results containing content
    """
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: exa_search_contents(query, text, highlights, num_results)
    )


async def exa_answer_async(
    query: str,
    text: bool = False
) -> Dict[str, Any]:
    """Async version of exa_answer.
    
    Args:
        query: The question to answer
        text: Include citation text
        
    Returns:
        Dict with answer and citations
    """
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: exa_answer(query, text)
    )


# Alias for simple usage
exa = exa_search


if __name__ == "__main__":
    # Example usage
    print("=" * 60)
    print("Exa Tools - Example Usage")
    print("=" * 60)
    
    is_available, error = _check_exa_available()
    if not is_available:
        print(f"\nExa is not available: {error}")
        print("\nTo use Exa tools:")
        print("1. Install the package: pip install exa_py")
        print("2. Set environment variable: export EXA_API_KEY=your_api_key")
    else:
        print("Exa SDK is available!")
        
        # Example search
        print("\n1. Basic Search")
        print("-" * 30)
        results = exa_search("Latest AI developments 2024", num_results=3)
        if "error" not in results:
            print(f"Found {len(results.get('results', []))} results")
            for r in results.get("results", [])[:3]:
                print(f"  - {r.get('title', 'No title')[:50]}...")
                print(f"    URL: {r.get('url', 'No URL')}")
        else:
            print(f"Error: {results['error']}")
        
        print("\n" + "=" * 60)
        print("Demonstration Complete")
        print("=" * 60)
