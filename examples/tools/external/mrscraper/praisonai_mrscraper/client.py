"""Synchronous MrScraper client for PraisonAI tool functions.

The request fields follow the MrScraper Python SDK. The official SDK is async;
this example keeps synchronous calls for ordinary PraisonAI Agent tools.
"""

from __future__ import annotations

import json
import os
from importlib import resources
from typing import Any, Dict, List, Mapping, Optional, Union
from urllib.parse import parse_qs, quote, urlparse

import httpx

Json = Union[Dict[str, Any], List[Any], str, int, float, bool, None]
Response = Dict[str, Any]
PLATFORM = "https://api.app.mrscraper.com"
SERP = "https://sync.scraper.mrscraper.com"
RENDER = "https://api.mrscraper.com"


class MrScraperError(RuntimeError):
    """Base error whose message never contains a token-bearing URL."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(MrScraperError):
    """Missing token or HTTP 401."""


class APIError(MrScraperError):
    """Other non-success HTTP status."""


class NetworkError(MrScraperError):
    """Transport failure or timeout."""


def _present(values: Mapping[str, Any]) -> Dict[str, Any]:
    """Omit only None, preserving False, zero, and empty strings."""
    return {key: value for key, value in values.items() if value is not None}


def _patterns(values: Optional[Union[str, List[str]]]) -> Optional[str]:
    if isinstance(values, list):
        return "||".join(values)
    return values


class MrScraperClient:
    """Call the MrScraper API with a token or MRSCRAPER_API_TOKEN.

    Methods return the SDK-style envelope: status_code, data, and headers.
    """

    def __init__(self, token: Optional[str] = None, *, http_timeout: float = 60.0,
                 transport: Optional[httpx.BaseTransport] = None) -> None:
        """Set HTTPX inactivity timeout, not an overall wall-clock deadline."""
        self._token = token or os.environ.get("MRSCRAPER_API_TOKEN")
        if not self._token or not self._token.strip():
            raise AuthenticationError("Set MRSCRAPER_API_TOKEN or pass token")
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
                 extra_headers: Optional[Mapping[str, str]] = None,
                 http_timeout: Optional[float] = None) -> Response:
        headers = {"Accept": "application/json", "x-api-token": self._token}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if host in (SERP, RENDER):
            headers["Authorization"] = f"Bearer {self._token}"
        headers.update(extra_headers or {})
        error: Optional[MrScraperError] = None
        try:
            timeout_options = {"timeout": http_timeout} if http_timeout is not None else {}
            response = self._http.request(method, host + path, headers=headers,
                                          params=params, json=body, **timeout_options)
            response.raise_for_status()
            data: Json = None
            if response.content:
                data = (response.json() if "json" in response.headers.get("Content-Type", "").lower()
                        else response.text)
            return {"status_code": response.status_code, "data": data,
                    "headers": dict(response.headers)}
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 401:
                error = AuthenticationError("MrScraper authentication failed (HTTP 401)", status)
            else:
                error = APIError(f"MrScraper HTTP {status} on {method} {host}{path}", status)
        except (httpx.RequestError, ValueError) as exc:
            # httpx errors can contain the rendered URL and its token query.
            error = NetworkError(f"MrScraper request failed on {method} {host}{path}: "
                                 f"{type(exc).__name__}")
        # Raising outside except prevents the raw httpx exception (and token)
        # from being attached as __context__.
        assert error is not None
        raise error

    @staticmethod
    def _serp_input(value: str) -> tuple[str, Optional[str], Optional[str], Optional[int]]:
        value = value.strip()
        if not value:
            raise ValueError("A Google query or URL is required")
        parsed = urlparse(value)
        if parsed.scheme.lower() not in ("http", "https"):
            return value, None, None, None
        params = parse_qs(parsed.query)
        query = (params.get("q") or [""])[0].strip()
        if not query:
            raise ValueError("Google search URL must contain q")
        try:
            start = int((params.get("start") or ["0"])[0])
        except ValueError:
            start = 0
        page = start // 10 + 1 if start > 0 else None
        return query, (params.get("gl") or [None])[0], (params.get("hl") or [None])[0], page

    # Primary methods mirror the Python SDK's operation names and request fields.
    def fetch_html(self, url: str, *, html: bool = True, markdown: bool = False,
                   timeout: int = 120, geo_code: str = "US",
                   proxy_country: Optional[str] = None,
                   block_resources: Optional[bool] = False,
                   browser_rendering: Optional[bool] = None,
                   super_mode: bool = False, use_proxy: bool = True,
                   proxy: Optional[str] = None,
                   wait_for_selector: Optional[str] = None,
                   home_page: bool = False, screenshot: bool = False,
                   bypass_proxy: bool = False,
                   cookie_jar: Optional[str] = None,
                   headers: Optional[Union[Dict[str, str], str]] = None,
                   max_retries: int = 3, token_cap: Optional[int] = None,
                   stream: Optional[bool] = None,
                   discard_token_secret: str = "") -> Response:
        """Fetch a page; all page controls are JSON body fields."""
        if not 1 <= timeout <= 300:
            raise ValueError("timeout must be between 1 and 300 seconds")
        if max_retries < 0 or (token_cap is not None and token_cap < 0):
            raise ValueError("max_retries and token_cap must be nonnegative")
        if not isinstance(screenshot, bool):
            raise ValueError("screenshot must be a boolean")
        body = _present({
            "token": self._token, "timeout": timeout, "geoCode": geo_code,
            "proxyCountry": proxy_country, "url": url,
            "browserRendering": browser_rendering, "super": super_mode,
            "useProxy": use_proxy, "proxy": proxy, "html": html,
            "markdown": markdown, "waitForSelector": wait_for_selector,
            "homePage": home_page, "screenshot": True if screenshot else None,
            "blockResources": block_resources, "bypassProxy": bypass_proxy,
            "cookieJar": cookie_jar, "headers": headers, "maxRetries": max_retries,
            "tokenCap": token_cap, "stream": stream,
        })
        extra = {"x-discard-token-secret": discard_token_secret} if discard_token_secret else None
        return self._request("POST", RENDER, "/", params={"screenshot": "true"} if screenshot else None,
                             body=body, extra_headers=extra, http_timeout=timeout + 30)

    def fetch_google_serp(self, url: str, *, raw: bool = True,
                          region: Optional[str] = None, language: Optional[str] = None,
                          page: Optional[int] = None, format: str = "json",
                          render_js: bool = False, timeout: float = 600.0) -> Response:
        """Search Google using terms or a Google search URL."""
        if format not in ("json", "html"):
            raise ValueError("format must be json or html")
        if page is not None and page < 1:
            raise ValueError("page must be positive")
        query, url_region, url_language, url_page = self._serp_input(url)
        body = _present({"query": query, "region": region or url_region,
                         "language": language or url_language, "page": page or url_page,
                         "format": "html" if raw else format, "renderJs": bool(render_js)})
        return self._request("POST", SERP, "/api/google/serp/v2/sync", body=body,
                             http_timeout=timeout)

    def create_scraper(self, url: str, message: Optional[str] = None, *,
                       agent: str = "general", mode: Optional[str] = None,
                       schema_prompt: Optional[Mapping[str, Any]] = None,
                       proxy_country: Optional[str] = None, home_page: bool = False,
                       max_depth: int = 2, max_pages: int = 50, limit: int = 1000,
                       include_patterns: str = "", exclude_patterns: str = "") -> Response:
        """Create and start a general, listing, or map AI scraper."""
        if agent not in ("general", "listing", "map"):
            raise ValueError("agent must be general, listing, or map")
        if mode is not None and mode not in ("Cheap", "Super"):
            raise ValueError("mode must be Cheap or Super")
        if agent in ("general", "listing"):
            if not message or not message.strip():
                raise ValueError("message is required for general and listing")
            resolved = message.strip()
            if schema_prompt is not None:
                resolved += ("\n\nBest-effort output guidance: return JSON matching this JSON Schema. "
                             "The MrScraper API does not validate this schema:\n"
                             + json.dumps(schema_prompt, indent=2))
            body = _present({"url": url, "message": resolved, "agent": agent,
                             "mode": mode, "proxyCountry": proxy_country,
                             "homePage": home_page,
                             "maxPages": max_pages if agent == "listing" else None})
        else:
            if message or schema_prompt is not None or proxy_country is not None:
                raise ValueError("map does not accept message, schema_prompt, or proxy_country")
            body = _present({"url": url, "agent": agent, "mode": mode,
                             "maxDepth": max_depth, "maxPages": max_pages, "limit": limit,
                             "includePatterns": include_patterns,
                             "excludePatterns": exclude_patterns})
        return self._request("POST", PLATFORM, "/api/v1/scrapers-ai", body=body)

    def rerun_scraper(self, scraper_id: str, url: str, *, max_depth: int = 2,
                      max_pages: int = 50, limit: int = 1000,
                      include_patterns: str = "", exclude_patterns: str = "",
                      proxy_country: Optional[str] = None,
                      max_retries: Optional[int] = None, timeout: Optional[int] = None,
                      home_page: bool = False, html: bool = False,
                      markdown: bool = False, screenshot: bool = False,
                      bypass_proxy: bool = False,
                      wait_for_selector: Optional[str] = None,
                      render_javascript: bool = False, use_proxy: bool = True,
                      proxy: Optional[str] = None, return_cookies: bool = False,
                      show_modal: bool = False, stream: bool = False) -> Response:
        """Rerun an AI scraper with the SDK's complete option set."""
        body = _present({
            "scraperId": scraper_id, "url": url, "maxDepth": max_depth,
            "maxPages": max_pages, "limit": limit,
            "includePatterns": include_patterns, "excludePatterns": exclude_patterns,
            "proxyCountry": proxy_country, "maxRetry": max_retries, "timeout": timeout,
            "useHomePage": home_page, "html": html, "markdown": markdown,
            "screenshot": screenshot, "bypassProxy": bypass_proxy,
            "waitForSelector": wait_for_selector, "renderJavascript": render_javascript,
            "useProxy": use_proxy, "proxy": proxy, "returnCookies": return_cookies,
            "showModal": show_modal, "stream": stream,
        })
        return self._request("POST", PLATFORM, "/api/v1/scrapers-ai-rerun", body=body)

    def bulk_rerun_ai_scraper(self, scraper_id: str, urls: List[str]) -> Response:
        """Rerun an AI scraper for multiple URLs."""
        self._check_urls(urls)
        return self._request("POST", PLATFORM, "/api/v1/scrapers-ai-rerun/bulk",
                             body={"scraperId": scraper_id, "urls": urls})

    def rerun_manual_scraper(self, scraper_id: str, url: str, *,
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
                             browser_flags: Optional[Mapping[str, Any]] = None,
                             token_cap: Optional[int] = None,
                             stream: Optional[bool] = None,
                             timeout: Optional[float] = None) -> Response:
        """Rerun a manual scraper with the SDK's complete option set."""
        if max_retries < 0:
            raise ValueError("max_retries must be nonnegative")
        body = _present({
            "scraperId": scraper_id, "url": url, "proxy": proxy,
            "proxyCountry": proxy_country, "maxRetry": max_retries,
            "maxRetries": max_retries, "returnCookie": return_cookies,
            "globalDomain": global_domain, "useProxy": use_proxy,
            "bypassProxy": bypass_proxy, "homePage": home_page,
            "homePageTimeout": home_page_timeout, "html": html,
            "markdown": markdown, "screenshot": screenshot,
            "cookieJar": cookie_jar, "browserFlags": browser_flags,
            "tokenCap": token_cap, "stream": stream, "timeout": timeout,
        })
        return self._request("POST", PLATFORM, "/api/v1/scrapers-manual-rerun", body=body)

    def bulk_rerun_manual_scraper(self, scraper_id: str, urls: List[str]) -> Response:
        """Rerun a manual scraper for multiple URLs."""
        self._check_urls(urls)
        return self._request("POST", PLATFORM, "/api/v1/scrapers-manual-rerun/bulk",
                             body={"scraperId": scraper_id, "urls": urls})

    @staticmethod
    def _check_urls(urls: List[str]) -> None:
        if not isinstance(urls, list) or not urls or any(
            not isinstance(url, str) or not url for url in urls
        ):
            raise ValueError("urls must be a nonempty list of URL strings")

    def get_all_results(self, *, sort_field: str = "updatedAt",
                        sort_order: str = "DESC", page_size: int = 10,
                        page: int = 1, search: Optional[str] = None,
                        date_range_column: Optional[str] = None,
                        start_at: Optional[str] = None, end_at: Optional[str] = None,
                        scraper_id: Optional[str] = None, status: Optional[str] = None,
                        type: Optional[str] = None, url: Optional[str] = None) -> Response:
        """List results with the SDK's sort, search, date, and field filters."""
        if sort_field not in ("createdAt", "updatedAt", "id", "type", "url", "status",
                              "error", "tokenUsage", "runtime"):
            raise ValueError("unsupported sort_field")
        if sort_order not in ("ASC", "DESC") or page < 1 or page_size < 1:
            raise ValueError("invalid sort_order, page, or page_size")
        params = _present({
            "sortField": sort_field, "sortOrder": sort_order,
            "pageSize": page_size, "page": page, "search": search,
            "dateRangeColumn": date_range_column, "startAt": start_at,
            "endAt": end_at, "filters[scraperId]": scraper_id,
            "filters[status]": status, "filters[type]": type,
            "filters[url]": url,
        })
        return self._request("GET", PLATFORM, "/api/v1/results", params=params)

    def get_result_by_id(self, result_id: str, *, include_html: bool = True) -> Response:
        """Get one result, optionally including its stored HTML."""
        return self._request("GET", PLATFORM, "/api/v1/results/" + quote(result_id, safe=""),
                             params={"includeHtml": str(include_html).lower()})

    def get_subscription_account(self) -> Response:
        """Get subscription and token usage."""
        return self._request("GET", PLATFORM, "/api/v1/subscription-accounts")

    def get_analytic_statuses(self, domain: str, start_date: str, end_date: str, *,
                              action: str = "", api_token_name: str = "") -> Response:
        """Get request outcome analytics for a domain and date range."""
        return self._request("GET", PLATFORM, "/api/v1/analytic/statuses", params={
            "domain": domain, "startDate": start_date, "endDate": end_date,
            "action": action, "apiTokenName": api_token_name})

    # Familiar names from the earlier n8n-based example remain as adapters.
    def get_account_info(self) -> Response:
        return self.get_subscription_account()

    def create_prompt_scraper(self, url: str, message: str, *, mode: Optional[str] = "Super",
                              proxy_country: Optional[str] = None,
                              output_schema: Optional[Mapping[str, Any]] = None,
                              home_page: bool = False) -> Response:
        return self.create_scraper(url, message, mode=mode, proxy_country=proxy_country,
                                   schema_prompt=output_schema, home_page=home_page)

    def extract_page_by_prompt(self, url: str, message: str, *, mode: Optional[str] = "Super",
                               proxy_country: Optional[str] = None,
                               output_schema: Optional[Mapping[str, Any]] = None,
                               home_page: bool = False) -> Response:
        return self.create_prompt_scraper(url, message, mode=mode,
                                          proxy_country=proxy_country,
                                          output_schema=output_schema, home_page=home_page)

    def create_listing_scraper(self, url: str, message: str, *, max_pages: int = 1,
                               proxy_country: Optional[str] = None,
                               item_schema: Optional[Mapping[str, Any]] = None,
                               mode: Optional[str] = None,
                               home_page: bool = False) -> Response:
        return self.create_scraper(url, message, agent="listing", max_pages=max_pages,
                                   schema_prompt=item_schema, proxy_country=proxy_country,
                                   mode=mode, home_page=home_page)

    def extract_listings(self, url: str, message: str, **kwargs: Any) -> Response:
        return self.create_listing_scraper(url, message, **kwargs)

    def create_crawl_scraper(self, url: str, *, max_depth: int = 2, max_pages: int = 50,
                             limit: int = 50,
                             include_patterns: Optional[Union[str, List[str]]] = None,
                             exclude_patterns: Optional[Union[str, List[str]]] = None,
                             mode: Optional[str] = None) -> Response:
        return self.create_scraper(
            url, agent="map", mode=mode, max_depth=max_depth, max_pages=max_pages,
            limit=limit, include_patterns=_patterns(include_patterns) or "",
            exclude_patterns=_patterns(exclude_patterns) or "")

    def crawl_website_urls(self, url: str, **kwargs: Any) -> Response:
        return self.create_crawl_scraper(url, **kwargs)

    def extract_structured_data(self, url: str, category: str, *,
                                mode: Optional[str] = "Super",
                                proxy_country: Optional[str] = None,
                                home_page: bool = False) -> Response:
        prompt_path = resources.files("praisonai_mrscraper").joinpath("structured_data_prompts.json")
        prompts = json.loads(prompt_path.read_text(encoding="utf-8"))
        if category not in prompts:
            raise ValueError(f"Unknown category; choose from {', '.join(sorted(prompts))}")
        return self.create_scraper(url, prompts[category], mode=mode,
                                   proxy_country=proxy_country, home_page=home_page)

    def search_google_serp(self, query: str, *, region: str = "us",
                           language: str = "en", page: int = 1,
                           format: str = "json", render_js: bool = False) -> Response:
        return self.fetch_google_serp(query, raw=False, region=region,
                                      language=language, page=page,
                                      format=format, render_js=render_js)

    def fetch_rendered_html(self, url: str, *, max_retries: int = 3,
                            page_timeout: int = 300, geo_code: str = "us",
                            html: bool = True, markdown: bool = False,
                            screenshot: Optional[Union[str, bool]] = None,
                            proxy_country: str = "us",
                            block_resources: Optional[bool] = None,
                            super_mode: Optional[bool] = None,
                            wait_for_selector: Optional[str] = None,
                            home_page: bool = False,
                            token_cap: Optional[int] = None) -> Response:
        if isinstance(screenshot, str) and screenshot not in ("full", "top"):
            raise ValueError("screenshot must be full, top, or a boolean")
        return self.fetch_html(url, max_retries=max_retries, timeout=page_timeout,
                               geo_code=geo_code, html=html, markdown=markdown,
                               screenshot=bool(screenshot), proxy_country=proxy_country,
                               block_resources=block_resources, super_mode=bool(super_mode),
                               wait_for_selector=wait_for_selector,
                               home_page=home_page, token_cap=token_cap)

    def get_results(self, scraper_id: str, *, page: int = 1, page_size: int = 10,
                    sort: str = "createdAt", sort_order: str = "DESC") -> Response:
        return self.get_all_results(scraper_id=scraper_id, page=page, page_size=page_size,
                                    sort_field=sort, sort_order=sort_order)

    def get_latest_results(self, scraper_id: str, *, page_size: int = 10) -> Response:
        return self.get_all_results(scraper_id=scraper_id, page_size=page_size,
                                    page=1, sort_field="createdAt", sort_order="DESC")

    def get_result_detail(self, result_id: str, *, include_html: bool = True) -> Response:
        return self.get_result_by_id(result_id, include_html=include_html)

    def run_existing_scraper(self, scraper_id: str, url: str, *,
                             scraper_type: str = "ai", agent_type: str = "general",
                             max_retry: int = 3, proxy_country: Optional[str] = None,
                             options: Optional[Mapping[str, Any]] = None) -> Response:
        """Compatibility adapter; prefer rerun_scraper or rerun_manual_scraper."""
        if scraper_type not in ("ai", "manual"):
            raise ValueError("scraper_type must be ai or manual")
        if agent_type not in ("general", "listing", "map"):
            raise ValueError("agent_type must be general, listing, or map")
        provided = dict(options or {})
        names = {
            "maxDepth": "max_depth", "maxPages": "max_pages", "limit": "limit",
            "includePatterns": "include_patterns", "excludePatterns": "exclude_patterns",
            "timeout": "timeout", "useHomePage": "home_page", "html": "html",
            "markdown": "markdown", "screenshot": "screenshot",
            "bypassProxy": "bypass_proxy", "waitForSelector": "wait_for_selector",
            "renderJavascript": "render_javascript", "useProxy": "use_proxy",
            "proxy": "proxy", "returnCookies": "return_cookies",
            "showModal": "show_modal", "stream": "stream",
            "cookieJar": "cookie_jar", "homePage": "home_page",
            "homePageTimeout": "home_page_timeout", "returnCookie": "return_cookies",
            "globalDomain": "global_domain", "browserFlags": "browser_flags",
            "tokenCap": "token_cap",
        }
        unknown = provided.keys() - names.keys()
        if unknown:
            raise ValueError(f"Unsupported rerun options: {', '.join(sorted(unknown))}")
        mapped = {names[key]: value for key, value in provided.items()}
        if scraper_type == "manual":
            if isinstance(mapped.get("screenshot"), bool):
                mapped["screenshot"] = str(mapped["screenshot"]).lower()
            return self.rerun_manual_scraper(
                scraper_id, url, max_retries=max_retry, proxy_country=proxy_country, **mapped)
        if isinstance(mapped.get("include_patterns"), list):
            mapped["include_patterns"] = _patterns(mapped["include_patterns"])
        if isinstance(mapped.get("exclude_patterns"), list):
            mapped["exclude_patterns"] = _patterns(mapped["exclude_patterns"])
        return self.rerun_scraper(
            scraper_id, url, max_retries=max_retry, proxy_country=proxy_country, **mapped)

    def run_existing_scraper_batch(self, scraper_id: str, urls: List[str], *,
                                   scraper_type: str = "ai") -> Response:
        if scraper_type == "ai":
            return self.bulk_rerun_ai_scraper(scraper_id, urls)
        if scraper_type == "manual":
            return self.bulk_rerun_manual_scraper(scraper_id, urls)
        raise ValueError("scraper_type must be ai or manual")
