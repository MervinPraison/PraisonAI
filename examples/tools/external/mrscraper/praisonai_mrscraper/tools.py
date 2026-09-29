"""Bounded, agent-callable wrappers around MrScraperClient."""

from __future__ import annotations

import json
from typing import Callable, List

from .client import MrScraperClient


def make_mrscraper_tools(client: MrScraperClient, *, max_chars: int = 12000) -> List[Callable[..., str]]:
    """Return callable tools for rendered pages, extraction, crawl, and search.

    Screenshot and cookie fields are deliberately not sent to an LLM context.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    def _without_sensitive(value: object) -> object:
        if isinstance(value, dict):
            return {key: _without_sensitive(item) for key, item in value.items()
                    if "screenshot" not in key.lower() and "cookie" not in key.lower()}
        if isinstance(value, list):
            return [_without_sensitive(item) for item in value]
        return value

    def _bounded(value: object) -> str:
        value = _without_sensitive(value)
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return raw[:max_chars]

    def read_web_page(url: str) -> str:
        """Read rendered Markdown from a public web page for a short summary."""
        return _bounded(client.fetch_rendered_html(url, html=False, markdown=True))

    def extract_page(url: str, prompt: str) -> str:
        """Ask MrScraper to extract information from one page using a prompt."""
        return _bounded(client.extract_page_by_prompt(url, prompt))

    def crawl_urls(url: str) -> str:
        """Discover URLs linked from a starting website."""
        return _bounded(client.crawl_website_urls(url))

    def search_google(query: str) -> str:
        """Search Google SERP with MrScraper and return bounded results."""
        return _bounded(client.search_google_serp(query))

    return [read_web_page, extract_page, crawl_urls, search_google]
