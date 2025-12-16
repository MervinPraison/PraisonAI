"""Crawl4AI web crawling and extraction tools.

Crawl4AI provides async web crawling with JavaScript rendering, content extraction,
and LLM-based data extraction capabilities.

Usage:
    from praisonaiagents.tools import crawl4ai, crawl4ai_extract
    
    # Simple crawl
    result = await crawl4ai("https://example.com")
    print(result["markdown"])
    
    # Extract structured data
    result = await crawl4ai_extract(
        "https://example.com/products",
        schema={"name": "Products", "baseSelector": ".product", ...}
    )
    
    # Or use the class directly
    from praisonaiagents.tools import Crawl4AITools
    tools = Crawl4AITools()
    result = await tools.crawl("https://example.com")
"""

from typing import List, Dict, Any, Optional, Union
import logging
import asyncio
from importlib import util


def _check_crawl4ai_available() -> tuple[bool, Optional[str]]:
    """Check if Crawl4AI is available.
    
    Returns:
        Tuple of (is_available, error_message)
    """
    if util.find_spec("crawl4ai") is None:
        return False, "crawl4ai package is not installed. Install it with: pip install crawl4ai && crawl4ai-setup"
    
    return True, None


class Crawl4AITools:
    """Crawl4AI web crawling and extraction tools.
    
    Provides methods for:
    - crawl: Basic web crawling with markdown output
    - crawl_many: Crawl multiple URLs concurrently
    - extract_css: Extract data using CSS selectors
    - extract_llm: Extract data using LLM
    
    Example:
        from praisonaiagents.tools import Crawl4AITools
        
        tools = Crawl4AITools()
        result = await tools.crawl("https://example.com")
        print(result["markdown"])
    """
    
    def __init__(
        self,
        headless: bool = True,
        verbose: bool = False,
        browser_type: str = "chromium"
    ):
        """Initialize Crawl4AITools.
        
        Args:
            headless: Run browser in headless mode (default True)
            verbose: Enable verbose logging (default False)
            browser_type: Browser type - "chromium", "firefox", or "webkit"
        """
        self.headless = headless
        self.verbose = verbose
        self.browser_type = browser_type
        self.logger = logging.getLogger(__name__)
        self._crawler = None
    
    async def _get_crawler(self):
        """Get or create AsyncWebCrawler instance."""
        is_available, error = _check_crawl4ai_available()
        if not is_available:
            raise ImportError(error)
        
        from crawl4ai import AsyncWebCrawler, BrowserConfig
        
        if self._crawler is None:
            browser_config = BrowserConfig(
                headless=self.headless,
                verbose=self.verbose,
                browser_type=self.browser_type
            )
            self._crawler = AsyncWebCrawler(config=browser_config)
            await self._crawler.start()
        
        return self._crawler
    
    async def close(self):
        """Close the crawler and release resources."""
        if self._crawler is not None:
            await self._crawler.close()
            self._crawler = None
    
    async def crawl(
        self,
        url: str,
        word_count_threshold: int = 10,
        css_selector: Optional[str] = None,
        excluded_tags: Optional[List[str]] = None,
        exclude_external_links: bool = False,
        js_code: Optional[Union[str, List[str]]] = None,
        wait_for: Optional[str] = None,
        screenshot: bool = False,
        pdf: bool = False,
        bypass_cache: bool = True
    ) -> Dict[str, Any]:
        """Crawl a single URL and return content.
        
        Args:
            url: The URL to crawl
            word_count_threshold: Minimum words per text block (default 10)
            css_selector: CSS selector to focus on specific content
            excluded_tags: HTML tags to exclude (e.g., ["nav", "footer"])
            exclude_external_links: Remove external links from content
            js_code: JavaScript code to execute before crawling
            wait_for: Wait condition - "css:selector" or "js:() => boolean"
            screenshot: Capture screenshot (base64)
            pdf: Generate PDF
            bypass_cache: Skip cache and fetch fresh content (default True)
            
        Returns:
            Dict with 'markdown', 'html', 'cleaned_html', 'links', 'media', etc.
        """
        try:
            crawler = await self._get_crawler()
            
            from crawl4ai import CrawlerRunConfig, CacheMode
            
            config = CrawlerRunConfig(
                word_count_threshold=word_count_threshold,
                css_selector=css_selector,
                excluded_tags=excluded_tags or [],
                exclude_external_links=exclude_external_links,
                js_code=js_code,
                wait_for=wait_for,
                screenshot=screenshot,
                pdf=pdf,
                cache_mode=CacheMode.BYPASS if bypass_cache else CacheMode.ENABLED
            )
            
            result = await crawler.arun(url=url, config=config)
            
            if not result.success:
                return {"error": f"Crawl failed: {result.error_message}", "success": False}
            
            response = {
                "success": True,
                "url": result.url,
                "markdown": result.markdown.raw_markdown if hasattr(result.markdown, 'raw_markdown') else str(result.markdown),
                "html": result.html,
                "cleaned_html": result.cleaned_html,
                "links": result.links,
                "media": result.media,
                "metadata": result.metadata
            }
            
            if hasattr(result.markdown, 'fit_markdown') and result.markdown.fit_markdown:
                response["fit_markdown"] = result.markdown.fit_markdown
            
            if screenshot and result.screenshot:
                response["screenshot"] = result.screenshot
            
            if pdf and result.pdf:
                response["pdf"] = result.pdf
            
            return response
            
        except Exception as e:
            self.logger.error(f"Crawl4AI crawl error: {e}")
            return {"error": f"Crawl4AI crawl error: {str(e)}", "success": False}
    
    async def crawl_many(
        self,
        urls: List[str],
        word_count_threshold: int = 10,
        css_selector: Optional[str] = None,
        bypass_cache: bool = True,
        stream: bool = False
    ) -> List[Dict[str, Any]]:
        """Crawl multiple URLs concurrently.
        
        Args:
            urls: List of URLs to crawl
            word_count_threshold: Minimum words per text block
            css_selector: CSS selector to focus on specific content
            bypass_cache: Skip cache and fetch fresh content
            stream: If True, returns async generator
            
        Returns:
            List of crawl results
        """
        try:
            crawler = await self._get_crawler()
            
            from crawl4ai import CrawlerRunConfig, CacheMode
            
            config = CrawlerRunConfig(
                word_count_threshold=word_count_threshold,
                css_selector=css_selector,
                cache_mode=CacheMode.BYPASS if bypass_cache else CacheMode.ENABLED,
                stream=stream
            )
            
            results = []
            
            if stream:
                async for result in await crawler.arun_many(urls, config=config):
                    if result.success:
                        results.append({
                            "success": True,
                            "url": result.url,
                            "markdown": result.markdown.raw_markdown if hasattr(result.markdown, 'raw_markdown') else str(result.markdown),
                            "html": result.html
                        })
                    else:
                        results.append({
                            "success": False,
                            "url": result.url,
                            "error": result.error_message
                        })
            else:
                raw_results = await crawler.arun_many(urls, config=config)
                for result in raw_results:
                    if result.success:
                        results.append({
                            "success": True,
                            "url": result.url,
                            "markdown": result.markdown.raw_markdown if hasattr(result.markdown, 'raw_markdown') else str(result.markdown),
                            "html": result.html
                        })
                    else:
                        results.append({
                            "success": False,
                            "url": result.url,
                            "error": result.error_message
                        })
            
            return results
            
        except Exception as e:
            self.logger.error(f"Crawl4AI crawl_many error: {e}")
            return [{"error": f"Crawl4AI crawl_many error: {str(e)}", "success": False}]
    
    async def extract_css(
        self,
        url: str,
        schema: Dict[str, Any],
        js_code: Optional[Union[str, List[str]]] = None,
        wait_for: Optional[str] = None,
        bypass_cache: bool = True
    ) -> Dict[str, Any]:
        """Extract structured data using CSS selectors.
        
        Args:
            url: The URL to crawl (or "raw://<html>" for raw HTML)
            schema: Extraction schema with baseSelector and fields
            js_code: JavaScript to execute before extraction
            wait_for: Wait condition before extraction
            bypass_cache: Skip cache
            
        Returns:
            Dict with 'data' containing extracted items
            
        Example schema:
            {
                "name": "Products",
                "baseSelector": "div.product",
                "fields": [
                    {"name": "title", "selector": "h2", "type": "text"},
                    {"name": "price", "selector": ".price", "type": "text"},
                    {"name": "link", "selector": "a", "type": "attribute", "attribute": "href"}
                ]
            }
        """
        try:
            crawler = await self._get_crawler()
            
            from crawl4ai import CrawlerRunConfig, CacheMode
            from crawl4ai.extraction_strategy import JsonCssExtractionStrategy
            
            extraction_strategy = JsonCssExtractionStrategy(schema, verbose=self.verbose)
            
            config = CrawlerRunConfig(
                extraction_strategy=extraction_strategy,
                js_code=js_code,
                wait_for=wait_for,
                cache_mode=CacheMode.BYPASS if bypass_cache else CacheMode.ENABLED
            )
            
            result = await crawler.arun(url=url, config=config)
            
            if not result.success:
                return {"error": f"Extraction failed: {result.error_message}", "success": False}
            
            import json
            try:
                data = json.loads(result.extracted_content) if result.extracted_content else []
            except json.JSONDecodeError:
                data = result.extracted_content
            
            return {
                "success": True,
                "url": result.url,
                "data": data,
                "count": len(data) if isinstance(data, list) else 1
            }
            
        except Exception as e:
            self.logger.error(f"Crawl4AI extract_css error: {e}")
            return {"error": f"Crawl4AI extract_css error: {str(e)}", "success": False}
    
    async def extract_llm(
        self,
        url: str,
        instruction: str,
        schema: Optional[Dict[str, Any]] = None,
        provider: str = "openai/gpt-4o-mini",
        api_token: Optional[str] = None,
        js_code: Optional[Union[str, List[str]]] = None,
        wait_for: Optional[str] = None,
        bypass_cache: bool = True
    ) -> Dict[str, Any]:
        """Extract structured data using LLM.
        
        Args:
            url: The URL to crawl
            instruction: Instructions for the LLM on what to extract
            schema: Optional Pydantic-style JSON schema for structured output
            provider: LLM provider string (e.g., "openai/gpt-4o-mini", "ollama/llama3.3")
            api_token: API token for the provider (uses env var if not provided)
            js_code: JavaScript to execute before extraction
            wait_for: Wait condition before extraction
            bypass_cache: Skip cache
            
        Returns:
            Dict with 'data' containing extracted content
        """
        try:
            crawler = await self._get_crawler()
            
            import os
            from crawl4ai import CrawlerRunConfig, CacheMode, LLMConfig
            from crawl4ai.extraction_strategy import LLMExtractionStrategy
            
            # Get API token from env if not provided
            if api_token is None and "openai" in provider.lower():
                api_token = os.environ.get("OPENAI_API_KEY")
            
            llm_config = LLMConfig(provider=provider, api_token=api_token)
            
            extraction_strategy = LLMExtractionStrategy(
                llm_config=llm_config,
                schema=schema,
                extraction_type="schema" if schema else "block",
                instruction=instruction,
                verbose=self.verbose
            )
            
            config = CrawlerRunConfig(
                extraction_strategy=extraction_strategy,
                js_code=js_code,
                wait_for=wait_for,
                cache_mode=CacheMode.BYPASS if bypass_cache else CacheMode.ENABLED
            )
            
            result = await crawler.arun(url=url, config=config)
            
            if not result.success:
                return {"error": f"LLM extraction failed: {result.error_message}", "success": False}
            
            import json
            try:
                data = json.loads(result.extracted_content) if result.extracted_content else None
            except json.JSONDecodeError:
                data = result.extracted_content
            
            return {
                "success": True,
                "url": result.url,
                "data": data
            }
            
        except Exception as e:
            self.logger.error(f"Crawl4AI extract_llm error: {e}")
            return {"error": f"Crawl4AI extract_llm error: {str(e)}", "success": False}


# Standalone async functions for easy access

async def crawl4ai(
    url: str,
    css_selector: Optional[str] = None,
    js_code: Optional[str] = None,
    wait_for: Optional[str] = None,
    screenshot: bool = False
) -> Dict[str, Any]:
    """Crawl a URL and return markdown content.
    
    Args:
        url: The URL to crawl
        css_selector: CSS selector to focus on specific content
        js_code: JavaScript to execute before crawling
        wait_for: Wait condition - "css:selector" or "js:() => boolean"
        screenshot: Capture screenshot
        
    Returns:
        Dict with 'markdown', 'html', 'links', 'media', etc.
        
    Example:
        result = await crawl4ai("https://example.com")
        print(result["markdown"])
    """
    is_available, error = _check_crawl4ai_available()
    if not is_available:
        logging.error(error)
        return {"error": error, "success": False}
    
    tools = Crawl4AITools()
    try:
        result = await tools.crawl(
            url=url,
            css_selector=css_selector,
            js_code=js_code,
            wait_for=wait_for,
            screenshot=screenshot
        )
        return result
    finally:
        await tools.close()


async def crawl4ai_many(
    urls: List[str],
    css_selector: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Crawl multiple URLs concurrently.
    
    Args:
        urls: List of URLs to crawl
        css_selector: CSS selector to focus on specific content
        
    Returns:
        List of crawl results
        
    Example:
        results = await crawl4ai_many(["https://example.com", "https://example.org"])
    """
    is_available, error = _check_crawl4ai_available()
    if not is_available:
        logging.error(error)
        return [{"error": error, "success": False}]
    
    tools = Crawl4AITools()
    try:
        return await tools.crawl_many(urls=urls, css_selector=css_selector)
    finally:
        await tools.close()


async def crawl4ai_extract(
    url: str,
    schema: Dict[str, Any],
    js_code: Optional[str] = None,
    wait_for: Optional[str] = None
) -> Dict[str, Any]:
    """Extract structured data using CSS selectors.
    
    Args:
        url: The URL to crawl
        schema: Extraction schema with baseSelector and fields
        js_code: JavaScript to execute before extraction
        wait_for: Wait condition before extraction
        
    Returns:
        Dict with 'data' containing extracted items
        
    Example:
        schema = {
            "name": "Products",
            "baseSelector": "div.product",
            "fields": [
                {"name": "title", "selector": "h2", "type": "text"},
                {"name": "price", "selector": ".price", "type": "text"}
            ]
        }
        result = await crawl4ai_extract("https://example.com/products", schema)
    """
    is_available, error = _check_crawl4ai_available()
    if not is_available:
        logging.error(error)
        return {"error": error, "success": False}
    
    tools = Crawl4AITools()
    try:
        return await tools.extract_css(
            url=url,
            schema=schema,
            js_code=js_code,
            wait_for=wait_for
        )
    finally:
        await tools.close()


async def crawl4ai_llm_extract(
    url: str,
    instruction: str,
    schema: Optional[Dict[str, Any]] = None,
    provider: str = "openai/gpt-4o-mini"
) -> Dict[str, Any]:
    """Extract data using LLM.
    
    Args:
        url: The URL to crawl
        instruction: Instructions for the LLM
        schema: Optional JSON schema for structured output
        provider: LLM provider (default "openai/gpt-4o-mini")
        
    Returns:
        Dict with 'data' containing extracted content
        
    Example:
        result = await crawl4ai_llm_extract(
            "https://example.com/about",
            instruction="Extract company name, founding year, and description"
        )
    """
    is_available, error = _check_crawl4ai_available()
    if not is_available:
        logging.error(error)
        return {"error": error, "success": False}
    
    tools = Crawl4AITools()
    try:
        return await tools.extract_llm(
            url=url,
            instruction=instruction,
            schema=schema,
            provider=provider
        )
    finally:
        await tools.close()


# Synchronous wrappers for convenience

def crawl4ai_sync(
    url: str,
    css_selector: Optional[str] = None,
    js_code: Optional[str] = None,
    wait_for: Optional[str] = None
) -> Dict[str, Any]:
    """Synchronous version of crawl4ai.
    
    Args:
        url: The URL to crawl
        css_selector: CSS selector to focus on specific content
        js_code: JavaScript to execute
        wait_for: Wait condition
        
    Returns:
        Dict with crawl results
    """
    return asyncio.get_event_loop().run_until_complete(
        crawl4ai(url, css_selector, js_code, wait_for)
    )


def crawl4ai_extract_sync(
    url: str,
    schema: Dict[str, Any],
    js_code: Optional[str] = None
) -> Dict[str, Any]:
    """Synchronous version of crawl4ai_extract.
    
    Args:
        url: The URL to crawl
        schema: Extraction schema
        js_code: JavaScript to execute
        
    Returns:
        Dict with extracted data
    """
    return asyncio.get_event_loop().run_until_complete(
        crawl4ai_extract(url, schema, js_code)
    )


if __name__ == "__main__":
    # Example usage
    async def main():
        print("=" * 60)
        print("Crawl4AI Tools - Example Usage")
        print("=" * 60)
        
        is_available, error = _check_crawl4ai_available()
        if not is_available:
            print(f"\nCrawl4AI is not available: {error}")
            print("\nTo use Crawl4AI tools:")
            print("1. Install the package: pip install crawl4ai")
            print("2. Run setup: crawl4ai-setup")
        else:
            print("Crawl4AI is available!")
            
            # Example crawl
            print("\n1. Basic Crawl")
            print("-" * 30)
            result = await crawl4ai("https://example.com")
            if result.get("success"):
                print(f"URL: {result['url']}")
                print(f"Markdown length: {len(result.get('markdown', ''))}")
                print(f"Links found: {len(result.get('links', {}).get('internal', []))}")
            else:
                print(f"Error: {result.get('error')}")
            
            print("\n" + "=" * 60)
            print("Demonstration Complete")
            print("=" * 60)
    
    asyncio.run(main())
