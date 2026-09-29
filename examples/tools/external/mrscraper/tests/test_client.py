"""Contract tests for the n8n routes, without paid API calls."""

import json

import httpx
import pytest

from praisonai_mrscraper import MrScraperClient, MrScraperError, make_mrscraper_tools


@pytest.fixture
def calls():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"data": {"sample": True}})

    return seen, httpx.MockTransport(respond)


def test_hosts_auth_and_verbs(calls):
    seen, transport = calls
    with MrScraperClient("private-token", transport=transport) as client:
        client.get_account_info()
        client.search_google_serp("example")
        client.fetch_rendered_html("https://example.com")
    account, serp, render = seen
    assert (account.method, account.url.host, account.url.path) == (
        "GET", "api.app.mrscraper.com", "/api/v1/subscription-accounts")
    assert account.headers["x-api-token"] == "private-token"
    assert (serp.method, serp.url.host, serp.url.path) == (
        "POST", "sync.scraper.mrscraper.com", "/api/google/serp/v2/sync")
    assert serp.headers["Authorization"] == "Bearer private-token"
    assert serp.headers["x-api-token"] == "private-token"
    assert json.loads(serp.content)["renderJs"] is False
    assert (render.method, render.url.host, render.url.path) == (
        "POST", "api.mrscraper.com", "/")
    assert render.url.params["token"] == "private-token"
    assert render.url.params["browserRendering"] == "true"
    assert json.loads(render.content) == {"url": "https://example.com", "maxRetries": 3}


def test_create_results_and_reruns(calls):
    seen, transport = calls
    with MrScraperClient("secret", transport=transport) as client:
        result = client.create_prompt_scraper("https://example.com", "Extract title",
                                              output_schema={"title": "string"})
        client.create_listing_scraper("https://example.com", "Extract links")
        client.crawl_website_urls("https://example.com", include_patterns=["/a", "/b"])
        client.get_results("id/a+b", page=2)
        client.get_result_detail("result/a+b")
        client.run_existing_scraper("s", "https://example.com", agent_type="listing",
                                    options={"stream": False})
        client.run_existing_scraper("s", "https://example.com", scraper_type="manual",
                                    options={"screenshot": True, "cookies": []})
        client.run_existing_scraper_batch("s", ["https://example.com"], scraper_type="manual")
    assert result == {"data": {"sample": True}}
    assert json.loads(seen[0].content)["graph"] == "general"
    assert "Return the output as JSON" in json.loads(seen[0].content)["message"]
    assert json.loads(seen[1].content)["maxPages"] == 1
    assert json.loads(seen[2].content)["includePatterns"] == "/a|/b"
    assert seen[3].url.params["filters[scraperId]"] == "id/a+b"
    assert seen[3].url.params["page"] == "2"
    assert seen[4].url.raw_path.startswith(b"/api/v1/results/result%2Fa%2Bb")
    assert json.loads(seen[5].content)["stream"] is False
    assert json.loads(seen[5].content)["maxPages"] == 5
    assert seen[6].url.path == "/api/v1/scrapers-manual-rerun"
    assert json.loads(seen[6].content)["screenshot"] == "true"
    assert json.loads(seen[7].content)["urls"] == ["https://example.com"]


def test_render_query_and_errors_are_sanitized():
    def fail(request):
        return httpx.Response(401, json={"error": "private-token"})

    with MrScraperClient("private-token", transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(MrScraperError) as error:
            client.fetch_rendered_html("https://example.com", html=False,
                                        markdown=True, screenshot="top", token_cap=20)
    assert error.value.status_code == 401
    assert "private-token" not in str(error.value)
    assert "token=" not in str(error.value)


def test_structured_preset_and_bounded_tools(calls):
    seen, transport = calls
    with MrScraperClient("secret", transport=transport) as client:
        client.extract_structured_data("https://example.com", "article")
        tools = make_mrscraper_tools(client, max_chars=25)
        assert len(tools[0]("https://example.com")) <= 25
    assert "headline" in json.loads(seen[0].content)["message"]
    assert seen[1].url.params["markdown"] == "true"
    assert seen[1].url.params["html"] == "false"


def test_invalid_options_do_not_make_requests(calls):
    seen, transport = calls
    with MrScraperClient("secret", transport=transport) as client:
        with pytest.raises(ValueError):
            client.run_existing_scraper_batch("s", [])
        with pytest.raises(ValueError):
            client.run_existing_scraper("s", "https://example.com", options={"bad": True})
        with pytest.raises(ValueError):
            client.extract_structured_data("https://example.com", "unknown")
    assert seen == []


def test_agent_tool_removes_nested_image_and_cookie_fields():
    def respond(request):
        return httpx.Response(200, json={"data": {"markdown": "Hello",
                                                  "screenshot": "base64-image",
                                                  "cookies": ["session-secret"]}})

    with MrScraperClient("secret", transport=httpx.MockTransport(respond)) as client:
        result = make_mrscraper_tools(client)[0]("https://example.com")
    assert "Hello" in result
    assert "base64-image" not in result
    assert "session-secret" not in result
