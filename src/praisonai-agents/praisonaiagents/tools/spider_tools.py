"""Tools for web scraping and crawling.

Usage:
from praisonaiagents.tools import spider_tools
content = spider_tools.scrape_page("https://example.com")
links = spider_tools.extract_links("https://example.com")

or
from praisonaiagents.tools import scrape_page, extract_links
content = scrape_page("https://example.com")
"""

import logging
from typing import List, Dict, Union, Optional, Any
from importlib import util
import json
from urllib.parse import urljoin, urlparse
import re
import os
import hashlib
import time

class SpiderTools:
    """Tools for web scraping and crawling."""
    
    def __init__(self):
        """Initialize SpiderTools and check for required packages."""
        self._session = None
        
    def _get_session(self):
        """Get or create requests session with common headers."""
        if util.find_spec('requests') is None:
            error_msg = "requests package is not available. Please install it using: pip install requests"
            logging.error(error_msg)
            return None
            
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (compatible; PraisonAI/1.0; +http://praisonai.com/bot)',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
            })
        return self._session

    def scrape_page(
        self,
        url: str,
        selector: Optional[str] = None,
        extract_images: bool = False,
        extract_links: bool = False,
        timeout: int = 30,
        verify_ssl: bool = True
    ) -> Union[Dict[str, Any], Dict[str, str]]:
        """
        Scrape content from a webpage.
        
        Args:
            url: URL to scrape
            selector: Optional CSS selector to extract specific content
            extract_images: Whether to extract image URLs
            extract_links: Whether to extract links
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
            
        Returns:
            Dict: Scraped content or error dict
        """
        try:
            session = self._get_session()
            if session is None:
                return {"error": "requests package not available"}

            # Import BeautifulSoup only when needed
            if util.find_spec('bs4') is None:
                error_msg = "bs4 package is not available. Please install it using: pip install beautifulsoup4"
                logging.error(error_msg)
                return {"error": error_msg}
            from bs4 import BeautifulSoup

            # Make request
            response = session.get(
                url,
                timeout=timeout,
                verify=verify_ssl
            )
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Remove unwanted elements
            for element in soup(['script', 'style']):
                element.decompose()
            
            # Initialize result
            result = {
                'url': url,
                'status_code': response.status_code,
                'encoding': response.encoding,
                'headers': dict(response.headers),
            }
            
            # Extract content based on selector
            if selector:
                elements = soup.select(selector)
                result['content'] = [elem.get_text(strip=True) for elem in elements]
                result['html'] = [str(elem) for elem in elements]
            else:
                result['title'] = soup.title.string if soup.title else None
                result['content'] = soup.get_text(separator=' ', strip=True)
                result['html'] = str(soup)
            
            # Extract metadata
            meta_tags = {}
            for meta in soup.find_all('meta'):
                name = meta.get('name') or meta.get('property')
                if name:
                    meta_tags[name] = meta.get('content')
            result['meta_tags'] = meta_tags
            
            # Extract images if requested
            if extract_images:
                images = []
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if src:
                        images.append({
                            'src': urljoin(url, src),
                            'alt': img.get('alt', ''),
                            'title': img.get('title', '')
                        })
                result['images'] = images
            
            # Extract links if requested
            if extract_links:
                links = []
                for link in soup.find_all('a'):
                    href = link.get('href')
                    if href:
                        links.append({
                            'url': urljoin(url, href),
                            'text': link.get_text(strip=True),
                            'title': link.get('title', '')
                        })
                result['links'] = links
            
            return result
        except Exception as e:
            error_msg = f"Error scraping {url}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def extract_links(
        self,
        url: str,
        same_domain: bool = True,
        exclude_patterns: Optional[List[str]] = None,
        timeout: int = 30,
        verify_ssl: bool = True
    ) -> Union[List[Dict[str, str]], Dict[str, str]]:
        """
        Extract all links from a webpage.
        
        Args:
            url: URL to extract links from
            same_domain: Only return links from the same domain
            exclude_patterns: List of regex patterns to exclude
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
            
        Returns:
            List[Dict] or Dict: List of links or error dict
        """
        try:
            # Compile exclude patterns
            if exclude_patterns:
                exclude_patterns = [re.compile(p) for p in exclude_patterns]
            
            # Get base domain
            base_domain = urlparse(url).netloc
            
            # Scrape page
            result = self.scrape_page(
                url,
                extract_links=True,
                timeout=timeout,
                verify_ssl=verify_ssl
            )
            
            if "error" in result:
                return result
            
            # Filter and clean links
            links = []
            seen_urls = set()
            
            for link in result.get('links', []):
                link_url = link['url']
                
                # Skip if already seen
                if link_url in seen_urls:
                    continue
                
                # Parse URL
                parsed = urlparse(link_url)
                
                # Skip if not same domain and same_domain is True
                if same_domain and parsed.netloc != base_domain:
                    continue
                
                # Skip if matches exclude patterns
                if exclude_patterns and any(p.search(link_url) for p in exclude_patterns):
                    continue
                
                # Add to results
                links.append(link)
                seen_urls.add(link_url)
            
            return links
        except Exception as e:
            error_msg = f"Error extracting links from {url}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def crawl(
        self,
        start_url: str,
        max_pages: int = 10,
        same_domain: bool = True,
        exclude_patterns: Optional[List[str]] = None,
        delay: float = 1.0,
        timeout: int = 30,
        verify_ssl: bool = True,
        output_dir: Optional[str] = None
    ) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """
        Crawl multiple pages starting from a URL.
        
        Args:
            start_url: Starting URL
            max_pages: Maximum number of pages to crawl
            same_domain: Only crawl pages from the same domain
            exclude_patterns: List of regex patterns to exclude
            delay: Delay between requests in seconds
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
            output_dir: Directory to save crawled pages
            
        Returns:
            List[Dict] or Dict: Crawled pages or error dict
        """
        try:
            # Create output directory if needed
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            
            # Initialize crawl state
            to_visit = {start_url}
            visited = set()
            results = []
            
            while to_visit and len(visited) < max_pages:
                # Get next URL
                url = to_visit.pop()
                
                # Skip if already visited
                if url in visited:
                    continue
                
                # Add to visited
                visited.add(url)
                
                # Delay if not first request
                if len(visited) > 1:
                    time.sleep(delay)
                
                # Scrape page
                result = self.scrape_page(
                    url,
                    extract_links=True,
                    timeout=timeout,
                    verify_ssl=verify_ssl
                )
                
                if "error" in result:
                    logging.warning(f"Error crawling {url}: {result['error']}")
                    continue
                
                # Save result
                results.append(result)
                
                # Save to file if requested
                if output_dir:
                    filename = hashlib.md5(url.encode()).hexdigest() + '.json'
                    filepath = os.path.join(output_dir, filename)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(result, f, indent=2, ensure_ascii=False)
                
                # Add new links to visit
                for link in result.get('links', []):
                    link_url = link['url']
                    parsed = urlparse(link_url)
                    
                    # Skip if not same domain and same_domain is True
                    if same_domain and parsed.netloc != urlparse(start_url).netloc:
                        continue
                    
                    # Skip if matches exclude patterns
                    if exclude_patterns and any(
                        re.compile(p).search(link_url) for p in exclude_patterns
                    ):
                        continue
                    
                    # Add to visit if not visited
                    if link_url not in visited:
                        to_visit.add(link_url)
            
            return results
        except Exception as e:
            error_msg = f"Error crawling from {start_url}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def extract_text(
        self,
        url: str,
        selector: Optional[str] = None,
        timeout: int = 30,
        verify_ssl: bool = True
    ) -> Union[str, Dict[str, str]]:
        """
        Extract clean text content from a webpage.
        
        Args:
            url: URL to extract text from
            selector: Optional CSS selector to extract specific content
            timeout: Request timeout in seconds
            verify_ssl: Whether to verify SSL certificates
            
        Returns:
            str or Dict: Extracted text or error dict
        """
        try:
            result = self.scrape_page(
                url,
                selector=selector,
                timeout=timeout,
                verify_ssl=verify_ssl
            )
            
            if "error" in result:
                return result
            
            if selector:
                return '\n'.join(result['content'])
            return result['content']
        except Exception as e:
            error_msg = f"Error extracting text from {url}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

# Create instance for direct function access
_spider_tools = SpiderTools()
scrape_page = _spider_tools.scrape_page
extract_links = _spider_tools.extract_links
crawl = _spider_tools.crawl
extract_text = _spider_tools.extract_text

if __name__ == "__main__":
    # Example usage
    print("\n==================================================")
    print("SpiderTools Demonstration")
    print("==================================================\n")
    
    # 1. Scrape a webpage
    print("1. Scraping Webpage")
    print("------------------------------")
    url = "https://example.com"
    result = scrape_page(url, extract_images=True, extract_links=True)
    print(f"Content from {url}:")
    if "error" not in result:
        print(f"Title: {result['title']}")
        print(f"Content length: {len(result['content'])} characters")
        print(f"Number of images: {len(result.get('images', []))}")
        print(f"Number of links: {len(result.get('links', []))}")
    else:
        print(result)  # Show error
    print()
    
    # 2. Extract links
    print("2. Extracting Links")
    print("------------------------------")
    links = extract_links(url)
    print(f"Links from {url}:")
    if isinstance(links, list):
        for link in links:
            print(f"- {link['url']} ({link['text']})")
    else:
        print(links)  # Show error
    print()
    
    # 3. Extract text
    print("3. Extracting Text")
    print("------------------------------")
    text = extract_text(url)
    print(f"Text from {url}:")
    if isinstance(text, str):
        print(text[:500] + "..." if len(text) > 500 else text)
    else:
        print(text)  # Show error
    print()
    
    # 4. Crawl multiple pages
    print("4. Crawling Multiple Pages")
    print("------------------------------")
    results = crawl(url, max_pages=2, delay=1.0)
    print(f"Crawl results from {url}:")
    if isinstance(results, list):
        print(f"Crawled {len(results)} pages")
        for result in results:
            print(f"- {result['url']}: {result['title']}")
    else:
        print(results)  # Show error
    
    print("\n==================================================")
    print("Demonstration Complete")
    print("==================================================")
