"""Agent-callable MrScraper functions backed by MrScraperClient."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Mapping, Optional, Union

from .client import MrScraperClient


def make_mrscraper_tools(client: MrScraperClient, *, max_chars: int = 12000,
                         include_all: bool = False) -> List[Callable[..., str]]:
    """Return four simple tools, or all SDK operation tools when include_all=True.

    Tools bound the response and exclude cookies, screenshots, tokens, and
    response headers before sending any content to a language model.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    def _without_sensitive(value: object) -> object:
        if isinstance(value, dict):
            def safe_key(key: object) -> bool:
                name = str(key).lower()
                return not (
                    any(part in name for part in (
                        "screenshot", "cookie", "authorization", "headers", "proxy", "secret"
                    )) or name == "token" or name.endswith("token")
                )
            return {key: _without_sensitive(item) for key, item in value.items()
                    if safe_key(key)}
        if isinstance(value, list):
            return [_without_sensitive(item) for item in value]
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return value
            if isinstance(decoded, (dict, list)):
                return _without_sensitive(decoded)
        return value

    def _bounded(value: object) -> str:
        value = _without_sensitive(value)
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return raw.replace(client._token, "[REDACTED]")[:max_chars]

    def read_web_page(url: str) -> str:
        """Read rendered Markdown from a public web page."""
        return _bounded(client.fetch_html(url, html=False, markdown=True))

    def extract_page(url: str, prompt: str) -> str:
        """Extract requested information from one web page."""
        return _bounded(client.create_scraper(url, prompt))

    def crawl_urls(url: str) -> str:
        """Discover URLs linked from a starting website."""
        return _bounded(client.create_scraper(url, agent="map"))

    def search_google(query: str) -> str:
        """Search Google and return parsed MrScraper SERP results."""
        return _bounded(client.fetch_google_serp(query, raw=False, format="json"))

    simple: List[Callable[..., str]] = [read_web_page, extract_page, crawl_urls, search_google]
    if not include_all:
        return simple

    def fetch_html(url: str, html: bool = True, markdown: bool = False,
                   timeout: int = 120, geo_code: str = "US",
                   proxy_country: Optional[str] = None,
                   block_resources: Optional[bool] = False,
                   browser_rendering: Optional[bool] = None,
                   super_mode: bool = False, use_proxy: bool = True,
                   proxy: Optional[str] = None,
                   wait_for_selector: Optional[str] = None,
                   home_page: bool = False, screenshot: bool = False,
                   bypass_proxy: bool = False, cookie_jar: Optional[str] = None,
                   headers: Optional[Union[Dict[str, str], str]] = None,
                   max_retries: int = 3, token_cap: Optional[int] = None,
                   stream: Optional[bool] = None,
                   discard_token_secret: str = "") -> str:
        """Fetch a web page with full MrScraper rendering options."""
        return _bounded(client.fetch_html(
            url, html=html, markdown=markdown, timeout=timeout, geo_code=geo_code,
            proxy_country=proxy_country, block_resources=block_resources,
            browser_rendering=browser_rendering, super_mode=super_mode,
            use_proxy=use_proxy, proxy=proxy, wait_for_selector=wait_for_selector,
            home_page=home_page, screenshot=screenshot, bypass_proxy=bypass_proxy,
            cookie_jar=cookie_jar, headers=headers, max_retries=max_retries,
            token_cap=token_cap, stream=stream,
            discard_token_secret=discard_token_secret))

    def fetch_google_serp(url: str, raw: bool = True, region: Optional[str] = None,
                          language: Optional[str] = None, page: Optional[int] = None,
                          format: str = "json", render_js: bool = False,
                          timeout: float = 600.0) -> str:
        """Search Google using query text or a Google search URL."""
        return _bounded(client.fetch_google_serp(
            url, raw=raw, region=region, language=language, page=page,
            format=format, render_js=render_js, timeout=timeout))

    def create_scraper(url: str, message: Optional[str] = None,
                       agent: str = "general", mode: Optional[str] = None,
                       schema_prompt: Optional[Dict[str, Any]] = None,
                       proxy_country: Optional[str] = None,
                       home_page: bool = False, max_depth: int = 2,
                       max_pages: int = 50, limit: int = 1000,
                       include_patterns: str = "", exclude_patterns: str = "") -> str:
        """Create and start a general, listing, or map AI scraper."""
        return _bounded(client.create_scraper(
            url, message, agent=agent, mode=mode, schema_prompt=schema_prompt,
            proxy_country=proxy_country, home_page=home_page,
            max_depth=max_depth, max_pages=max_pages, limit=limit,
            include_patterns=include_patterns, exclude_patterns=exclude_patterns))

    def rerun_scraper(scraper_id: str, url: str, max_depth: int = 2,
                      max_pages: int = 50, limit: int = 1000,
                      include_patterns: str = "", exclude_patterns: str = "",
                      proxy_country: Optional[str] = None,
                      max_retries: Optional[int] = None,
                      timeout: Optional[int] = None, home_page: bool = False,
                      html: bool = False, markdown: bool = False,
                      screenshot: bool = False, bypass_proxy: bool = False,
                      wait_for_selector: Optional[str] = None,
                      render_javascript: bool = False, use_proxy: bool = True,
                      proxy: Optional[str] = None, return_cookies: bool = False,
                      show_modal: bool = False, stream: bool = False) -> str:
        """Run an existing AI scraper on one URL."""
        return _bounded(client.rerun_scraper(
            scraper_id, url, max_depth=max_depth, max_pages=max_pages,
            limit=limit, include_patterns=include_patterns,
            exclude_patterns=exclude_patterns, proxy_country=proxy_country,
            max_retries=max_retries, timeout=timeout, home_page=home_page,
            html=html, markdown=markdown, screenshot=screenshot,
            bypass_proxy=bypass_proxy, wait_for_selector=wait_for_selector,
            render_javascript=render_javascript, use_proxy=use_proxy,
            proxy=proxy, return_cookies=return_cookies, show_modal=show_modal,
            stream=stream))

    def bulk_rerun_ai_scraper(scraper_id: str, urls: List[str]) -> str:
        """Run an existing AI scraper on multiple URLs."""
        return _bounded(client.bulk_rerun_ai_scraper(scraper_id, urls))

    def rerun_manual_scraper(scraper_id: str, url: str,
                             proxy: Optional[str] = None,
                             proxy_country: Optional[str] = None,
                             max_retries: int = 3, return_cookies: bool = False,
                             global_domain: bool = True, use_proxy: bool = True,
                             bypass_proxy: bool = True, home_page: bool = False,
                             home_page_timeout: Optional[int] = 10,
                             html: Optional[bool] = False,
                             markdown: Optional[bool] = False,
                             screenshot: Optional[str] = None,
                             cookie_jar: Optional[str] = None,
                             browser_flags: Optional[Dict[str, Any]] = None,
                             token_cap: Optional[int] = None,
                             stream: Optional[bool] = None,
                             timeout: Optional[float] = None) -> str:
        """Run an existing manual scraper on one URL."""
        return _bounded(client.rerun_manual_scraper(
            scraper_id, url, proxy=proxy, proxy_country=proxy_country,
            max_retries=max_retries, return_cookies=return_cookies,
            global_domain=global_domain, use_proxy=use_proxy,
            bypass_proxy=bypass_proxy, home_page=home_page,
            home_page_timeout=home_page_timeout, html=html, markdown=markdown,
            screenshot=screenshot, cookie_jar=cookie_jar,
            browser_flags=browser_flags, token_cap=token_cap, stream=stream,
            timeout=timeout))

    def bulk_rerun_manual_scraper(scraper_id: str, urls: List[str]) -> str:
        """Run an existing manual scraper on multiple URLs."""
        return _bounded(client.bulk_rerun_manual_scraper(scraper_id, urls))

    def get_all_results(sort_field: str = "updatedAt", sort_order: str = "DESC",
                        page_size: int = 10, page: int = 1,
                        search: Optional[str] = None,
                        date_range_column: Optional[str] = None,
                        start_at: Optional[str] = None, end_at: Optional[str] = None,
                        scraper_id: Optional[str] = None, status: Optional[str] = None,
                        type: Optional[str] = None, url: Optional[str] = None) -> str:
        """List scraping results with sorting, search, and filters."""
        return _bounded(client.get_all_results(
            sort_field=sort_field, sort_order=sort_order, page_size=page_size,
            page=page, search=search, date_range_column=date_range_column,
            start_at=start_at, end_at=end_at, scraper_id=scraper_id,
            status=status, type=type, url=url))

    def get_result_by_id(result_id: str, include_html: bool = True) -> str:
        """Get one stored result by ID."""
        return _bounded(client.get_result_by_id(result_id, include_html=include_html))

    def get_subscription_account() -> str:
        """Get MrScraper account, subscription, and token usage."""
        return _bounded(client.get_subscription_account())

    def get_analytic_statuses(domain: str, start_date: str, end_date: str,
                              action: str = "", api_token_name: str = "") -> str:
        """Get request status analytics for a domain and date range."""
        return _bounded(client.get_analytic_statuses(
            domain, start_date, end_date, action=action,
            api_token_name=api_token_name))

    return simple + [
        fetch_html, fetch_google_serp, create_scraper, rerun_scraper,
        bulk_rerun_ai_scraper, rerun_manual_scraper, bulk_rerun_manual_scraper,
        get_all_results, get_result_by_id, get_subscription_account,
        get_analytic_statuses,
    ]
