"""Trafilatura tools for high-quality URL content extraction.

Usage:
from praisonaiagents.tools import trafilatura_tools
content = trafilatura_tools.extract_content("https://example.com/article")
metadata = trafilatura_tools.extract_metadata("https://example.com/article")

or
from praisonaiagents.tools import extract_content, extract_metadata
content = extract_content("https://example.com/article")
"""

import logging
from typing import Dict, Any, Optional, Union
from importlib import util
import json
from urllib.parse import urlparse

class TrafilaturaTools:
    """Tools for extracting high-quality content from URLs using Trafilatura."""
    
    def __init__(self):
        """Initialize TrafilaturaTools and check for trafilatura package."""
        self._check_trafilatura()
        
    def _check_trafilatura(self):
        """Check if trafilatura package is installed."""
        if util.find_spec("trafilatura") is None:
            raise ImportError("trafilatura package is not available. Please install it using: pip install trafilatura")
        global trafilatura
        import trafilatura
        
    def _validate_url(self, url: str) -> bool:
        """
        Validate URL to prevent SSRF attacks.
        
        Args:
            url: URL to validate
            
        Returns:
            bool: True if URL is safe, False otherwise
        """
        try:
            parsed = urlparse(url)
            
            # Only allow http/https protocols
            if parsed.scheme not in ['http', 'https']:
                return False
            
            # Reject URLs with no hostname
            if not parsed.hostname:
                return False
            
            # Reject local/internal addresses
            hostname = parsed.hostname.lower()
            
            # Block localhost and loopback
            if hostname in ['localhost', '127.0.0.1', '0.0.0.0', '::1']:
                return False
            
            # Block private IP ranges
            import ipaddress
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                    return False
            except ValueError:
                # Not an IP address, continue with domain validation
                pass
            
            # Block common internal domains
            if any(hostname.endswith(domain) for domain in ['.local', '.internal', '.localdomain']):
                return False
            
            # Block metadata service endpoints
            if hostname in ['169.254.169.254', 'metadata.google.internal']:
                return False
            
            return True
            
        except Exception:
            return False

    def extract_content(
        self,
        url: str,
        include_comments: bool = False,
        include_links: bool = True,
        output_format: str = 'json',
        include_metadata: bool = True,
        target_language: Optional[str] = None
    ) -> Union[Dict[str, Any], str]:
        """
        Extract high-quality content from a URL using Trafilatura.
        
        Args:
            url: URL to extract content from
            include_comments: Include comments in extraction
            include_links: Include links in extraction
            output_format: Output format ('json', 'text', 'xml')
            include_metadata: Include metadata in extraction
            target_language: Target language for extraction (None for auto-detect)
            
        Returns:
            Dict or str: Extracted content (dict for json format, str for text/xml)
        """
        # Validate URL
        if not self._validate_url(url):
            error_msg = f"Invalid or unsafe URL: {url}"
            logging.error(error_msg)
            return {"error": error_msg} if output_format == 'json' else error_msg
        
        try:
            # Fetch the URL content
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                error_msg = f"Could not fetch content from URL: {url}"
                logging.error(error_msg)
                return {"error": error_msg} if output_format == 'json' else error_msg
            
            # Extract content
            extracted = trafilatura.extract(
                downloaded,
                include_comments=include_comments,
                include_links=include_links,
                output_format=output_format,
                with_metadata=include_metadata,
                url=url,
                target_language=target_language
            )
            
            if not extracted:
                error_msg = f"Could not extract readable content from: {url}"
                logging.warning(error_msg)
                return {"error": error_msg} if output_format == 'json' else error_msg
            
            # Parse JSON output if requested
            if output_format == 'json':
                return json.loads(extracted)
            else:
                return extracted
                
        except Exception as e:
            error_msg = f"Error extracting content from {url}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg} if output_format == 'json' else error_msg

    def extract_metadata(
        self,
        url: str
    ) -> Dict[str, Any]:
        """
        Extract metadata from a URL.
        
        Args:
            url: URL to extract metadata from
            
        Returns:
            Dict: Metadata including title, author, date, etc.
        """
        # Validate URL
        if not self._validate_url(url):
            error_msg = f"Invalid or unsafe URL: {url}"
            logging.error(error_msg)
            return {"error": error_msg}
        
        try:
            # Fetch the URL content
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                error_msg = f"Could not fetch content from URL: {url}"
                logging.error(error_msg)
                return {"error": error_msg}
            
            # Extract metadata
            metadata = trafilatura.extract_metadata(downloaded, url=url)
            
            if not metadata:
                return {
                    "url": url,
                    "error": "No metadata found"
                }
            
            # Convert metadata object to dict
            result = {
                "url": url,
                "title": metadata.title,
                "author": metadata.author,
                "date": metadata.date,
                "description": metadata.description,
                "categories": metadata.categories,
                "tags": metadata.tags,
                "language": metadata.language,
                "image": metadata.image,
                "pagetype": metadata.pagetype,
                "license": metadata.license
            }
            
            # Remove None values
            result = {k: v for k, v in result.items() if v is not None}
            
            return result
            
        except Exception as e:
            error_msg = f"Error extracting metadata from {url}: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}

    def extract_text_only(
        self,
        url: str,
        include_comments: bool = False
    ) -> str:
        """
        Extract only the main text content from a URL.
        
        Args:
            url: URL to extract text from
            include_comments: Include comments in extraction
            
        Returns:
            str: Extracted text content
        """
        result = self.extract_content(
            url=url,
            include_comments=include_comments,
            include_links=False,
            output_format='text',
            include_metadata=False
        )
        return result

    def compare_extraction(
        self,
        url: str,
        include_newspaper: bool = True,
        include_spider: bool = True
    ) -> Dict[str, Any]:
        """
        Compare Trafilatura extraction with other tools for the same URL.
        
        Args:
            url: URL to extract content from
            include_newspaper: Include newspaper3k comparison
            include_spider: Include spider_tools comparison
            
        Returns:
            Dict: Comparison of extraction results
        """
        comparison = {
            "url": url,
            "trafilatura": None,
            "newspaper": None,
            "spider": None
        }
        
        # Get Trafilatura extraction
        try:
            comparison["trafilatura"] = self.extract_content(url)
        except Exception as e:
            comparison["trafilatura"] = {"error": str(e)}
        
        # Get Newspaper extraction if requested
        if include_newspaper:
            try:
                from praisonaiagents.tools import get_article
                comparison["newspaper"] = get_article(url)
            except Exception as e:
                comparison["newspaper"] = {"error": str(e)}
        
        # Get Spider extraction if requested
        if include_spider:
            try:
                from praisonaiagents.tools import scrape_page
                comparison["spider"] = scrape_page(url)
            except Exception as e:
                comparison["spider"] = {"error": str(e)}
        
        return comparison

# Create module-level instances
_tools = TrafilaturaTools()

# Expose methods at module level
def extract_content(
    url: str,
    include_comments: bool = False,
    include_links: bool = True,
    output_format: str = 'json',
    include_metadata: bool = True,
    target_language: Optional[str] = None
) -> Union[Dict[str, Any], str]:
    """Extract high-quality content from a URL using Trafilatura."""
    return _tools.extract_content(
        url=url,
        include_comments=include_comments,
        include_links=include_links,
        output_format=output_format,
        include_metadata=include_metadata,
        target_language=target_language
    )

def extract_metadata(url: str) -> Dict[str, Any]:
    """Extract metadata from a URL."""
    return _tools.extract_metadata(url)

def extract_text_only(url: str, include_comments: bool = False) -> str:
    """Extract only the main text content from a URL."""
    return _tools.extract_text_only(url=url, include_comments=include_comments)

def compare_extraction(
    url: str,
    include_newspaper: bool = True,
    include_spider: bool = True
) -> Dict[str, Any]:
    """Compare Trafilatura extraction with other tools for the same URL."""
    return _tools.compare_extraction(
        url=url,
        include_newspaper=include_newspaper,
        include_spider=include_spider
    )

# For direct module usage
def __call__(url: str, **kwargs) -> Union[Dict[str, Any], str]:
    """Direct call to extract content."""
    return extract_content(url, **kwargs)

# Test the tool
if __name__ == "__main__":
    # Test URL
    test_url = "https://www.python.org/about/"
    
    print("Testing Trafilatura Tools")
    print("=" * 50)
    
    # Test 1: Extract content
    print("\n1. Testing extract_content():")
    print("-" * 50)
    try:
        content = extract_content(test_url)
        if isinstance(content, dict) and 'error' not in content:
            print(f"✓ Title: {content.get('title', 'N/A')}")
            print(f"✓ Language: {content.get('language', 'N/A')}")
            print(f"✓ Text length: {len(content.get('text', ''))} characters")
            print(f"✓ Author: {content.get('author', 'N/A')}")
            print(f"✓ Date: {content.get('date', 'N/A')}")
        else:
            print(f"✗ Error: {content}")
    except Exception as e:
        print(f"✗ Exception: {e}")
    
    # Test 2: Extract metadata
    print("\n2. Testing extract_metadata():")
    print("-" * 50)
    try:
        metadata = extract_metadata(test_url)
        if isinstance(metadata, dict) and 'error' not in metadata:
            print("✓ Metadata extracted successfully:")
            for key, value in metadata.items():
                if key != 'url':
                    print(f"  - {key}: {value}")
        else:
            print(f"✗ Error: {metadata}")
    except Exception as e:
        print(f"✗ Exception: {e}")
    
    # Test 3: Extract text only
    print("\n3. Testing extract_text_only():")
    print("-" * 50)
    try:
        text = extract_text_only(test_url)
        if isinstance(text, str) and not text.startswith("Could not"):
            print(f"✓ Text extracted: {len(text)} characters")
            print(f"✓ Preview: {text[:150]}...")
        else:
            print(f"✗ Error: {text}")
    except Exception as e:
        print(f"✗ Exception: {e}")
    
    # Test 4: Test URL validation
    print("\n4. Testing URL validation (security):")
    print("-" * 50)
    unsafe_urls = ["http://localhost/test", "http://127.0.0.1/test"]
    for unsafe_url in unsafe_urls:
        try:
            result = extract_content(unsafe_url)
            if isinstance(result, dict) and 'error' in result and 'Invalid or unsafe URL' in result['error']:
                print(f"✓ Correctly rejected: {unsafe_url}")
            else:
                print(f"✗ Failed to reject: {unsafe_url}")
        except Exception as e:
            print(f"✗ Exception for {unsafe_url}: {e}")
    
    print("\n" + "=" * 50)
    print("Trafilatura Tools testing complete!")