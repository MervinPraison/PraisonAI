"""Use Xquik tweet search as a PraisonAI custom tool.

Set XQUIK_API_KEY before running this example. The tool calls the public
Xquik tweet search endpoint and returns compact tweet summaries for the agent.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from praisonaiagents import Agent, tool


XQUIK_SEARCH_URL = "https://xquik.com/api/v1/x/tweets/search"


def _as_record(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _tweet_line(tweet: dict[str, Any]) -> str:
    author_field = (
        tweet.get("author_username")
        or tweet.get("username")
        or _as_record(tweet.get("author")).get("username")
    )
    author = _as_text(author_field)
    text = _as_text(
        tweet.get("text") or tweet.get("full_text") or tweet.get("content")
    )
    tweet_id = _as_text(tweet.get("id") or tweet.get("tweet_id"))
    prefix = f"@{author}: " if author else ""
    suffix = f" ({tweet_id})" if tweet_id else ""
    return f"{prefix}{text}{suffix}".strip()


def _bounded_limit(value: Any) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return 5
    return max(1, min(parsed, 10))


@tool(
    availability=lambda: (
        bool(os.environ.get("XQUIK_API_KEY")),
        "Set XQUIK_API_KEY before using search_x_posts.",
    )
)
def search_x_posts(query: str, limit: int = 5) -> str:
    """Search recent public X posts with Xquik."""
    api_key = os.environ.get("XQUIK_API_KEY")
    if not api_key:
        return "Set XQUIK_API_KEY before using search_x_posts."

    query_text = _as_text(query)
    if not query_text:
        return "Provide a non-empty query before using search_x_posts."

    bounded_limit = _bounded_limit(limit)
    params = {"q": query_text, "limit": bounded_limit, "queryType": "Latest"}
    url = f"{XQUIK_SEARCH_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        return f"Xquik returned HTTP {error.code}."
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        return f"Xquik search failed: {error.__class__.__name__}."

    tweets = _as_record(payload).get("tweets")
    if not isinstance(tweets, list) or not tweets:
        return "No posts found."

    lines = [_tweet_line(_as_record(tweet)) for tweet in tweets[:bounded_limit]]
    return "\n".join(line for line in lines if line) or "No readable posts found."


agent = Agent(
    instructions="You find recent public X posts and summarize the useful patterns.",
    tools=[search_x_posts],
)


if __name__ == "__main__":
    agent.start("Search X for recent AI agent framework discussions.")
