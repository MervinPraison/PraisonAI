"""Small synchronous client for the MrScraper n8n operation contract.

The platform's response envelopes are passed through because they vary by API.
"""

from __future__ import annotations

import json
import os
from importlib import resources
from typing import Any, Dict, List, Mapping, Optional, Union
from urllib.parse import quote

import httpx

Json = Union[Dict[str, Any], List[Any], str, int, float, bool, None]
PLATFORM = "https://api.app.mrscraper.com"
SERP = "https://sync.scraper.mrscraper.com"
RENDER = "https://api.mrscraper.com"


class MrScraperError(RuntimeError):
    """Sanitized HTTP or transport failure; never includes a token-bearing URL."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _present(values: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _patterns(values: Optional[List[str]]) -> Optional[str]:
    return "|".join(values) if values is not None else None


class MrScraperClient:
    """Call MrScraper with a token from the environment or constructor.

    ``http_timeout`` controls the Python request deadline. API ``timeout``
    options control page loading and are sent independently.
    """

    def __init__(self, token: Optional[str] = None, *, http_timeout: float = 60.0,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        self._token = token or os.environ.get("MRSCRAPER_API_TOKEN")
        if not self._token:
            raise ValueError("Set MRSCRAPER_API_TOKEN or pass token")
        self._http = httpx.Client(timeout=http_timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "MrScraperClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(self, method: str, host: str, path: str, *,
                 params: Optional[Mapping[str, Any]] = None,
                 body: Optional[Mapping[str, Any]] = None,
                 timeout: Optional[float] = None) -> Json:
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if host == SERP:
            headers["Authorization"] = f"Bearer {self._token}"
            # The n8n credential adds this header to every route as well.
            headers["x-api-token"] = self._token
        else:
            headers["x-api-token"] = self._token
        request_kwargs: Dict[str, Any] = {"headers": headers, "params": params, "json": body}
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        error: Optional[MrScraperError] = None
        try:
            response = self._http.request(method, host + path, **request_kwargs)
            response.raise_for_status()
            if not response.content:
                return None
            if "json" in response.headers.get("Content-Type", ""):
                return response.json()
            return response.text
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            error = MrScraperError(f"MrScraper HTTP {status} on {method} {host}{path}", status)
        except (httpx.RequestError, ValueError) as exc:
            # httpx errors can contain the rendered URL and its token query.
            error = MrScraperError(f"MrScraper request failed on {method} {host}{path}: {type(exc).__name__}")
        # Raise outside the except block so the original token-bearing exception
        # is not attached via __context__/__cause__ and cannot leak the token.
        raise error

    def get_account_info(self) -> Json:
        """Get subscription account details from the platform host."""
        return self._request("GET", PLATFORM, "/api/v1/subscription-accounts")

    def create_prompt_scraper(self, url: str, message: str, *, mode: str = "Super",
                              proxy_country: Optional[str] = None,
                              output_schema: Optional[Mapping[str, Any]] = None) -> Json:
        """Create a general AI scraper; append an optional expected JSON shape to its prompt."""
        if mode not in ("Super", "Cheap"):
            raise ValueError("mode must be Super or Cheap")
        if output_schema is not None:
            message += "\n\nReturn the output as JSON matching this schema:\n" + json.dumps(output_schema)
        return self._request("POST", PLATFORM, "/api/v1/scrapers-ai", body=_present({
            "graph": "general", "url": url, "message": message, "mode": mode,
            "proxyCountry": proxy_country}))

    def extract_page_by_prompt(self, url: str, message: str, *, mode: str = "Super",
                               proxy_country: Optional[str] = None,
                               output_schema: Optional[Mapping[str, Any]] = None) -> Json:
        """Create and start the same general scraper used by prompt-based creation."""
        return self.create_prompt_scraper(url, message, mode=mode,
                                          proxy_country=proxy_country,
                                          output_schema=output_schema)

    def create_listing_scraper(self, url: str, message: str, *, max_pages: int = 1,
                               proxy_country: Optional[str] = None,
                               item_schema: Optional[Mapping[str, Any]] = None) -> Json:
        """Create a listing scraper with pagination and optional item shape."""
        if item_schema is not None:
            message += "\n\nReturn each item as JSON matching this schema:\n" + json.dumps(item_schema)
        return self._request("POST", PLATFORM, "/api/v1/scrapers-ai", body=_present({
            "graph": "listing", "url": url, "message": message,
            "maxPages": max_pages, "proxyCountry": proxy_country}))

    def extract_listings(self, url: str, message: str, *, max_pages: int = 1,
                         proxy_country: Optional[str] = None,
                         item_schema: Optional[Mapping[str, Any]] = None) -> Json:
        """Create and start the same listing scraper used by listing creation."""
        return self.create_listing_scraper(url, message, max_pages=max_pages,
                                           proxy_country=proxy_country,
                                           item_schema=item_schema)

    def create_crawl_scraper(self, url: str, *, max_depth: int = 2,
                             max_pages: int = 50, limit: int = 50,
                             include_patterns: Optional[List[str]] = None,
                             exclude_patterns: Optional[List[str]] = None) -> Json:
        """Create a map scraper that discovers URLs from a starting page."""
        return self._request("POST", PLATFORM, "/api/v1/scrapers-ai", body=_present({
            "graph": "map", "url": url, "maxDepth": max_depth,
            "maxPages": max_pages, "limit": limit,
            "includePatterns": _patterns(include_patterns),
            "excludePatterns": _patterns(exclude_patterns)}))

    def crawl_website_urls(self, url: str, *, max_depth: int = 2,
                           max_pages: int = 50, limit: int = 50,
                           include_patterns: Optional[List[str]] = None,
                           exclude_patterns: Optional[List[str]] = None) -> Json:
        """Create and start the same map scraper used by crawl creation."""
        return self.create_crawl_scraper(url, max_depth=max_depth,
                                         max_pages=max_pages, limit=limit,
                                         include_patterns=include_patterns,
                                         exclude_patterns=exclude_patterns)

    def extract_structured_data(self, url: str, category: str, *, mode: str = "Super",
                                proxy_country: Optional[str] = None) -> Json:
        """Create a general scraper with a local n8n preset prompt for ``category``."""
        prompt_path = resources.files("praisonai_mrscraper").joinpath("structured_data_prompts.json")
        prompts = json.loads(prompt_path.read_text(encoding="utf-8"))
        if category not in prompts:
            raise ValueError(f"Unknown category; choose from {', '.join(sorted(prompts))}")
        return self.create_prompt_scraper(url, prompts[category], mode=mode,
                                          proxy_country=proxy_country)

    def search_google_serp(self, query: str, *, region: str = "us", language: str = "en",
                           page: int = 1, format: str = "json",
                           render_js: bool = False) -> Json:
        """Search Google with MrScraper's synchronous SERP endpoint."""
        if format not in ("json", "html"):
            raise ValueError("format must be json or html")
        return self._request("POST", SERP, "/api/google/serp/v2/sync", body={
            "query": query, "region": region, "language": language,
            "page": page, "format": format, "renderJs": render_js})

    def fetch_rendered_html(self, url: str, *, max_retries: int = 3,
                            page_timeout: int = 300, geo_code: str = "us",
                            html: bool = True, markdown: bool = False,
                            screenshot: Optional[str] = None, proxy_country: str = "us",
                            block_resources: Optional[bool] = None,
                            return_cookie: Optional[bool] = None,
                            super_mode: Optional[bool] = None,
                            wait_for_selector: Optional[str] = None,
                            wait_until: Optional[str] = None,
                            home_page: Optional[str] = None,
                            token_cap: Optional[int] = None) -> Json:
        """Fetch a rendered page; page controls are distinct from HTTP timeout."""
        if screenshot is not None and screenshot not in ("full", "top"):
            raise ValueError("screenshot must be full or top")
        if wait_until is not None and wait_until not in ("domcontentloaded", "load", "networkidle"):
            raise ValueError("unsupported wait_until")
        query = _present({"token": self._token, "browserRendering": True,
                          "timeout": page_timeout, "geoCode": geo_code,
                          "html": html, "markdown": markdown, "screenshot": screenshot,
                          "proxyCountry": proxy_country, "blockResources": block_resources,
                          "returnCookie": return_cookie, "super": super_mode,
                          "waitForSelector": wait_for_selector, "waitUntil": wait_until})
        query = {key: str(value).lower() if isinstance(value, bool) else value
                 for key, value in query.items()}
        # Give the synchronous render the page timeout it requested, plus a
        # buffer for network transfer, so the HTTP client does not abort early.
        http_timeout = float(page_timeout) + 30.0
        return self._request("POST", RENDER, "/", params=query, timeout=http_timeout,
                             body=_present({
            "url": url, "maxRetries": max_retries, "homePage": home_page,
            "tokenCap": token_cap}))

    def get_results(self, scraper_id: str, *, page: int = 1, page_size: int = 10,
                    sort: str = "createdAt", sort_order: str = "DESC") -> Json:
        """List results for a scraper with URL-encoded query parameters."""
        return self._request("GET", PLATFORM, "/api/v1/results", params={
            "filters[scraperId]": scraper_id, "page": page, "pageSize": page_size,
            "sort": sort, "sortOrder": sort_order})

    def get_latest_results(self, scraper_id: str, *, page_size: int = 10) -> Json:
        """List newest results for a scraper."""
        return self.get_results(scraper_id, page=1, page_size=page_size,
                                sort="createdAt", sort_order="DESC")

    def get_result_detail(self, result_id: str) -> Json:
        """Fetch one result by its URL-encoded ID."""
        return self._request("GET", PLATFORM,
                             "/api/v1/results/" + quote(result_id, safe=""))

    def run_existing_scraper(self, scraper_id: str, url: str, *,
                             scraper_type: str = "ai", agent_type: str = "general",
                             max_retry: int = 3, proxy_country: Optional[str] = None,
                             options: Optional[Mapping[str, Any]] = None) -> Json:
        """Rerun an AI or manual scraper; options are validated per scraper type."""
        if scraper_type not in ("ai", "manual"):
            raise ValueError("scraper_type must be ai or manual")
        if agent_type not in ("general", "listing", "map"):
            raise ValueError("agent_type must be general, listing, or map")
        common = {"bypassProxy", "html", "markdown", "screenshot"}
        general = common | {"renderJavascript", "returnCookies", "useHomePage", "waitForSelector"}
        listing = general | {"maxPages", "timeout", "stream"}
        mapping = general if agent_type == "general" else listing if agent_type == "listing" else {
            "maxDepth", "maxPages", "limit", "includePatterns", "excludePatterns"}
        manual = {"bypassProxy", "cookieJar", "cookies", "homePage", "homePageTimeout",
                  "html", "markdown", "paginator", "proxy", "record", "returnCookie",
                  "screenshot", "stream", "timeout", "tokenCap"}
        provided = dict(options or {})
        unknown = provided.keys() - (manual if scraper_type == "manual" else mapping)
        if unknown:
            raise ValueError(f"Unsupported rerun options: {', '.join(sorted(unknown))}")
        if scraper_type == "ai" and agent_type == "listing":
            provided = {"maxPages": 5, "timeout": 300, **provided}
        if scraper_type == "ai" and agent_type == "map":
            provided = {"maxDepth": 2, "maxPages": 50, "limit": 50, **provided}
        for key in ("includePatterns", "excludePatterns"):
            if isinstance(provided.get(key), list):
                provided[key] = _patterns(provided[key])
        if scraper_type == "manual" and "screenshot" in provided:
            if not isinstance(provided["screenshot"], bool):
                raise ValueError("manual screenshot must be a boolean")
            provided["screenshot"] = str(provided["screenshot"]).lower()
        route = "/api/v1/scrapers-ai-rerun" if scraper_type == "ai" else "/api/v1/scrapers-manual-rerun"
        return self._request("POST", PLATFORM, route, body={**_present({
            "scraperId": scraper_id, "url": url, "maxRetry": max_retry,
            "proxyCountry": proxy_country}), **provided})

    def run_existing_scraper_batch(self, scraper_id: str, urls: List[str], *,
                                   scraper_type: str = "ai") -> Json:
        """Rerun an AI or manual scraper for a nonempty list of URLs."""
        if scraper_type not in ("ai", "manual"):
            raise ValueError("scraper_type must be ai or manual")
        if not isinstance(urls, list) or not urls or any(
            not isinstance(url, str) or not url for url in urls
        ):
            raise ValueError("urls must be a nonempty list of URL strings")
        route = "/api/v1/scrapers-ai-rerun/bulk" if scraper_type == "ai" else "/api/v1/scrapers-manual-rerun/bulk"
        return self._request("POST", PLATFORM, route, body={"scraperId": scraper_id,
                                                             "urls": urls})
