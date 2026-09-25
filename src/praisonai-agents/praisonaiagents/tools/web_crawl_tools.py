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
from praisonaiagents._logging import get_logger
from typing import Any, Dict, List, Optional, Union

logger = get_logger(__name__)

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
                if not _is_safe_crawl_url(url):
                    results.append({
                        "url": url,
                        "content": "",
                        "error": "URL blocked by SSRF policy",
                        "provider": "crawl4ai",
                    })
                    continue
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

def _is_safe_crawl_url(url: str) -> bool:
    """Return True when a URL passes SSRF checks for crawling."""
    from praisonaiagents.tools.url_safety import is_safe_http_url

    return is_safe_http_url(url)


def _fence_for(text: str) -> str:
    """Return a backtick fence long enough to safely wrap ``text``.

    Markdown fenced blocks must use a run of backticks longer than any run that
    appears in the enclosed content, otherwise the content closes the fence
    early. Minimum length is three.
    """
    import re

    longest = 0
    for match in re.finditer(r"`+", text):
        longest = max(longest, len(match.group(0)))
    return "`" * max(3, longest + 1)


def _inline_code(text: str) -> str:
    """Wrap ``text`` as inline code, choosing a delimiter that survives backticks."""
    import re

    longest = 0
    for match in re.finditer(r"`+", text):
        longest = max(longest, len(match.group(0)))
    delim = "`" * (longest + 1)
    if longest:
        # Pad with spaces so a leading/trailing backtick does not merge with the
        # delimiter (CommonMark rule for inline code spans).
        return f"{delim} {text} {delim}"
    return f"{delim}{text}{delim}"


def _html_to_markdown(html: str, base_url: Optional[str] = None) -> tuple:
    """Convert HTML to lightweight Markdown using only the standard library.

    Preserves headings, lists, links (with targets), and fenced code blocks so
    that structure survives the dependency-free fetch path. Returns a tuple of
    ``(markdown, title)``.

    ``base_url`` is used to resolve relative link targets so preserved links
    point at their intended page.
    """
    from html.parser import HTMLParser
    from html import unescape
    import urllib.parse
    import re

    # Sentinel markers wrap fenced code regions so post-processing whitespace
    # cleanup can skip them without altering whitespace-sensitive examples.
    _CODE_OPEN = "\x00CODE_OPEN\x00"
    _CODE_CLOSE = "\x00CODE_CLOSE\x00"

    class _MarkdownParser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts: List[str] = []
            self.title = ""
            self._skip_depth = 0
            self._in_title = False
            self._in_pre = 0
            self._in_code = 0
            self._li_depth = 0
            self._href: Optional[str] = None
            self._link_start: Optional[int] = None
            self._pre_buffer: Optional[List[str]] = None
            self._code_buffer: Optional[List[str]] = None
            self._list_stack: List[Dict[str, Any]] = []

        _SKIP_TAGS = {"script", "style", "head", "noscript"}
        _BLOCK_TAGS = {
            "p", "div", "section", "article", "header", "footer", "main",
            "table", "tr", "blockquote", "ul", "ol",
        }

        def _newline(self, count: int = 1) -> None:
            self.parts.append("\n" * count)

        def handle_starttag(self, tag, attrs):
            if tag in self._SKIP_TAGS:
                self._skip_depth += 1
                if tag == "head":
                    # still want <title> inside head
                    self._skip_depth -= 1
                    return
                return
            if self._skip_depth:
                return
            if tag == "title":
                self._in_title = True
                return
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                level = int(tag[1])
                self._newline(2)
                self.parts.append("#" * level + " ")
            elif tag == "pre":
                self._in_pre += 1
                if self._in_pre == 1:
                    # Buffer raw text so the closing fence length can be chosen
                    # to be longer than any backtick run inside the block.
                    self._pre_buffer = []
            elif tag == "code":
                self._in_code += 1
                if not self._in_pre and self._code_buffer is None:
                    self._code_buffer = []
            elif tag == "a":
                attr = dict(attrs)
                self._href = attr.get("href")
                self._link_start = len(self.parts)
                self.parts.append("[")
            elif tag in ("ul", "ol"):
                self._list_stack.append({"ordered": tag == "ol", "index": 0})
                self._newline()
            elif tag == "li":
                self._li_depth += 1
                self._newline()
                indent = "  " * (len(self._list_stack) - 1) if self._list_stack else ""
                if self._list_stack and self._list_stack[-1]["ordered"]:
                    self._list_stack[-1]["index"] += 1
                    self.parts.append(f"{indent}{self._list_stack[-1]['index']}. ")
                else:
                    self.parts.append(f"{indent}- ")
            elif tag == "br":
                if not self._li_depth:
                    self._newline()
                else:
                    self.parts.append(" ")
            elif tag in ("strong", "b"):
                self.parts.append("**")
            elif tag in ("em", "i"):
                self.parts.append("*")
            elif tag in self._BLOCK_TAGS:
                # Inside a list item, block children (e.g. <p>) must not split the
                # bullet from its text; keep them on the same line. Only insert a
                # separating space when the marker line already has content so we
                # don't produce a double space right after the bullet.
                if self._li_depth:
                    if self.parts and not self.parts[-1].endswith((" ", "\n")):
                        self.parts.append(" ")
                else:
                    self._newline(2)

        def handle_endtag(self, tag):
            if tag in self._SKIP_TAGS and tag != "head":
                if self._skip_depth:
                    self._skip_depth -= 1
                return
            if self._skip_depth:
                return
            if tag == "title":
                self._in_title = False
                return
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self._newline(2)
            elif tag == "pre":
                if self._in_pre:
                    self._in_pre -= 1
                if self._in_pre == 0 and self._pre_buffer is not None:
                    body = "".join(self._pre_buffer).strip("\n")
                    fence = _fence_for(body)
                    self._newline(2)
                    self.parts.append(f"{_CODE_OPEN}{fence}\n{body}\n{fence}{_CODE_CLOSE}")
                    self._newline(2)
                    self._pre_buffer = None
            elif tag == "code":
                if self._in_code:
                    self._in_code -= 1
                if not self._in_pre and self._code_buffer is not None:
                    self.parts.append(_inline_code("".join(self._code_buffer)))
                    self._code_buffer = None
            elif tag == "a":
                target = self._resolve_href(self._href)
                if target:
                    self.parts.append(f"]({target})")
                else:
                    # no usable href: drop the opening bracket to keep plain text
                    if self._link_start is not None and self._link_start < len(self.parts):
                        self.parts[self._link_start] = ""
                self._href = None
                self._link_start = None
            elif tag in ("ul", "ol"):
                if self._list_stack:
                    self._list_stack.pop()
                self._newline()
            elif tag == "li":
                if self._li_depth:
                    self._li_depth -= 1
            elif tag in ("strong", "b"):
                self.parts.append("**")
            elif tag in ("em", "i"):
                self.parts.append("*")
            elif tag in self._BLOCK_TAGS:
                if not self._li_depth:
                    self._newline(2)

        def _resolve_href(self, href: Optional[str]) -> Optional[str]:
            if not href:
                return None
            href = href.strip()
            if not href:
                return None
            if base_url:
                try:
                    href = urllib.parse.urljoin(base_url, href)
                except Exception:
                    pass
            # Escape characters that would prematurely terminate a Markdown link
            # target so the destination stays intact.
            return href.replace(" ", "%20").replace("(", "%28").replace(")", "%29")

        def handle_data(self, data):
            if self._skip_depth:
                return
            if self._in_title:
                self.title += data
                return
            if self._pre_buffer is not None:
                self._pre_buffer.append(data)
            elif self._code_buffer is not None:
                self._code_buffer.append(data)
            else:
                self.parts.append(data)

    parser = _MarkdownParser()
    parser.feed(html)
    parser.close()

    markdown = "".join(parser.parts)

    # Split out fenced code regions so whitespace cleanup never touches them.
    segments = re.split(f"({re.escape(_CODE_OPEN)}.*?{re.escape(_CODE_CLOSE)})", markdown, flags=re.DOTALL)
    rebuilt: List[str] = []
    for segment in segments:
        if segment.startswith(_CODE_OPEN):
            rebuilt.append(segment[len(_CODE_OPEN):-len(_CODE_CLOSE)])
            continue
        # Collapse excessive blank lines and trailing spaces per line (prose only).
        lines = [line.rstrip() for line in segment.split("\n")]
        cleaned: List[str] = []
        blank_run = 0
        for line in lines:
            if line.strip():
                blank_run = 0
                cleaned.append(line)
            else:
                blank_run += 1
                if blank_run <= 2:
                    cleaned.append("")
        rebuilt.append("\n".join(cleaned))

    markdown = "".join(rebuilt).strip()
    return markdown, unescape(parser.title).strip()


def _crawl_with_httpx(urls: List[str]) -> List[Dict[str, Any]]:
    """Crawl URLs using basic HTTP fetch with httpx or urllib."""
    import urllib.parse
    results = []
    redirect_statuses = {301, 302, 303, 307, 308}
    max_redirects = 5

    for url in urls:
        base_url = url
        try:
            # Try httpx first
            try:
                import httpx
                current = url
                response = None
                with httpx.Client(follow_redirects=False, timeout=30.0) as client:
                    for _ in range(max_redirects + 1):
                        if not _is_safe_crawl_url(current):
                            raise ValueError("Redirect target failed SSRF validation")
                        response = client.get(current)
                        if response.status_code not in redirect_statuses:
                            break
                        location = response.headers.get("Location")
                        if not location:
                            break
                        current = urllib.parse.urljoin(current, location)
                    else:
                        raise ValueError("Too many redirects")
                if response is not None:
                    response.raise_for_status()
                    content = response.text
                    base_url = current
            except ImportError:
                # Fallback to urllib
                import urllib.request
                if not _is_safe_crawl_url(url):
                    raise ValueError("URL blocked by SSRF policy")
                with urllib.request.urlopen(url, timeout=30) as response:
                    content = response.read().decode('utf-8', errors='ignore')
            
            # Convert HTML to structured Markdown using the standard library so
            # headings, lists, links, and code blocks survive on this path.
            try:
                content, title = _html_to_markdown(content, base_url=base_url)
            except Exception:
                # Fall back to the flat-text extraction so the tool never fails.
                import re
                raw = content
                raw = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL | re.IGNORECASE)
                raw = re.sub(r'<style[^>]*>.*?</style>', '', raw, flags=re.DOTALL | re.IGNORECASE)
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', raw, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else ""
                raw = re.sub(r'<[^>]+>', ' ', raw)
                content = re.sub(r'\s+', ' ', raw).strip()

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
    if single_url and ',' in urls:
        # LLM may pass comma-separated URLs as a single string
        raw_url_list = [u.strip() for u in urls.split(',') if u.strip()]
        single_url = len(raw_url_list) == 1
    else:
        raw_url_list = [urls] if single_url else urls

    # Validate URLs to prevent SSRF and Local File Read
    url_list = []
    for u in raw_url_list:
        if _is_safe_crawl_url(u):
            url_list.append(u)
        else:
            logger.warning(f"Rejected unsafe crawl URL: {u}")
            
    if not url_list:
        return {"error": "No valid or safe URLs provided. Local and non-http(s) URLs are blocked for security."}

    
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
