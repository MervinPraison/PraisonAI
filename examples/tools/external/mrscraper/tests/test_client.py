"""Mocked request tests for the MrScraper Python SDK wire contract."""

import inspect
import json

import httpx
import pytest

from praisonai_mrscraper import (
    APIError, AuthenticationError, MrScraperClient, NetworkError, make_mrscraper_tools,
)


@pytest.fixture
def calls():
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json={"data": {"sample": True}},
                              headers={"set-cookie": "secret-cookie"})

    return seen, httpx.MockTransport(respond)


def body(request):
    return json.loads(request.content)


def test_auth_hosts_envelope_and_serp_url(calls):
    seen, transport = calls
    with MrScraperClient("private-token", transport=transport) as client:
        result = client.get_subscription_account()
        client.fetch_google_serp(
            "https://www.google.com/search?q=hotels&gl=id&hl=en&start=10",
            raw=False, format="json", render_js=False)
        client.fetch_html("https://example.com", screenshot=True,
                          discard_token_secret="discard-key")
    account, serp, render = seen
    assert result["status_code"] == 200
    assert result["data"] == {"data": {"sample": True}}
    assert account.url.host == "api.app.mrscraper.com"
    assert account.headers["x-api-token"] == "private-token"
    assert serp.url.host == "sync.scraper.mrscraper.com"
    assert serp.headers["Authorization"] == "Bearer private-token"
    assert serp.headers["x-api-token"] == "private-token"
    assert body(serp) == {"query": "hotels", "region": "id", "language": "en",
                          "page": 2, "format": "json", "renderJs": False}
    assert render.url.host == "api.mrscraper.com"
    assert render.url.params["screenshot"] == "true"
    assert render.headers["Authorization"] == "Bearer private-token"
    assert render.headers["x-discard-token-secret"] == "discard-key"
    assert body(render)["token"] == "private-token"
    assert body(render)["screenshot"] is True
    assert body(render)["timeout"] == 120
    assert "browserRendering" not in body(render)


def test_fetch_html_complete_body_preserves_false_zero_empty(calls):
    seen, transport = calls
    with MrScraperClient("secret", transport=transport) as client:
        client.fetch_html(
            "https://example.com", timeout=30, geo_code="ID",
            proxy_country="GB", block_resources=False, browser_rendering=False,
            super_mode=True, use_proxy=False, proxy="proxy:80", html=False,
            markdown=True, wait_for_selector="#ready", home_page=True,
            screenshot=False, bypass_proxy=True, cookie_jar="",
            headers={"X-Test": "1"}, max_retries=0, token_cap=0, stream=False)
    request = seen[0]
    assert not request.url.params
    assert body(request) == {
        "token": "secret", "timeout": 30, "geoCode": "ID", "proxyCountry": "GB",
        "url": "https://example.com", "browserRendering": False, "super": True,
        "useProxy": False, "proxy": "proxy:80", "html": False, "markdown": True,
        "waitForSelector": "#ready", "homePage": True, "blockResources": False,
        "bypassProxy": True, "cookieJar": "", "headers": {"X-Test": "1"},
        "maxRetries": 0, "tokenCap": 0, "stream": False,
    }


def test_create_all_agents_and_presets(calls):
    seen, transport = calls
    with MrScraperClient("secret", transport=transport) as client:
        client.create_scraper("https://example.com", "Extract title",
                              schema_prompt={"title": "string"}, home_page=True)
        client.create_scraper("https://example.com", "Get products",
                              agent="listing", max_pages=5, mode="Cheap")
        client.create_scraper("https://example.com", agent="map", limit=1000,
                              include_patterns="/a||/b", exclude_patterns="/login")
        client.extract_structured_data("https://example.com", "article")
        client.create_crawl_scraper("https://example.com",
                                    include_patterns=["/a", "/b"])
    general, listing, mapping, preset, legacy = map(body, seen)
    assert general["agent"] == "general" and "graph" not in general
    assert general["homePage"] is True
    assert "Best-effort output guidance" in general["message"]
    assert "mode" not in general
    assert listing["maxPages"] == 5 and listing["mode"] == "Cheap"
    assert "homePage" not in mapping
    assert mapping["limit"] == 1000
    assert mapping["includePatterns"] == "/a||/b"
    assert "headline" in preset["message"]
    assert legacy["includePatterns"] == "/a||/b"
    assert legacy["limit"] == 50
    with MrScraperClient("secret", transport=transport) as client:
        with pytest.raises(ValueError):
            client.create_scraper("https://example.com", agent="map", message="wrong")


def test_rerun_ai_manual_bulk_and_result_filters(calls):
    seen, transport = calls
    with MrScraperClient("secret", transport=transport) as client:
        client.rerun_scraper(
            "ai-id", "https://example.com", max_depth=0, max_pages=0,
            limit=0, include_patterns="", max_retries=0, timeout=0,
            home_page=True, use_proxy=False, show_modal=True, stream=False)
        client.rerun_manual_scraper(
            "manual-id", "https://example.com", max_retries=0,
            global_domain=False, use_proxy=False, bypass_proxy=False,
            screenshot="top", browser_flags={"headless": True},
            token_cap=0, stream=False, timeout=0)
        client.bulk_rerun_ai_scraper("ai-id", ["https://example.com/a"])
        client.bulk_rerun_manual_scraper("manual-id", ["https://example.com/b"])
        client.get_all_results(
            sort_field="runtime", page=2, search="", scraper_id="id/a+b",
            status="done", type="ai", url="https://example.com/a",
            date_range_column="updatedAt", start_at="2026-01-01", end_at="2026-01-31")
        client.get_result_by_id("result/a+b", include_html=False)
        client.get_analytic_statuses("example.com", "2026-01-01", "2026-01-31")
    ai, manual, bulk_ai, bulk_manual, results, detail, analytics = seen
    assert body(ai)["maxDepth"] == 0 and body(ai)["maxRetry"] == 0
    assert body(ai)["useProxy"] is False and body(ai)["showModal"] is True
    assert body(manual)["maxRetry"] == body(manual)["maxRetries"] == 0
    assert body(manual)["browserFlags"] == {"headless": True}
    assert body(manual)["screenshot"] == "top"
    assert bulk_ai.url.path.endswith("/scrapers-ai-rerun/bulk")
    assert bulk_manual.url.path.endswith("/scrapers-manual-rerun/bulk")
    assert results.url.params["sortField"] == "runtime"
    assert results.url.params["filters[scraperId]"] == "id/a+b"
    assert results.url.params["search"] == ""
    assert detail.url.raw_path.startswith(b"/api/v1/results/result%2Fa%2Bb")
    assert detail.url.params["includeHtml"] == "false"
    assert analytics.url.params["action"] == ""
    assert analytics.url.params["apiTokenName"] == ""


def test_all_agent_tools_and_redaction(calls):
    seen, transport = calls
    with MrScraperClient("private-token", transport=transport) as client:
        simple = make_mrscraper_tools(client)
        assert [tool.__name__ for tool in simple] == [
            "read_web_page", "extract_page", "crawl_urls", "search_google"]
        all_tools = make_mrscraper_tools(client, include_all=True)
        assert len(all_tools) == 15
        assert len({tool.__name__ for tool in all_tools}) == 15
        names = {tool.__name__: tool for tool in all_tools}
        assert "schema_prompt" in inspect.signature(names["create_scraper"]).parameters
        assert "browser_flags" in inspect.signature(names["rerun_manual_scraper"]).parameters
        assert "date_range_column" in inspect.signature(names["get_all_results"]).parameters
        output = names["fetch_html"]("https://example.com", markdown=True)
        assert "set-cookie" not in output and "private-token" not in output
        names["get_analytic_statuses"]("example.com", "2026-01-01", "2026-01-31")
    assert body(seen[0])["markdown"] is True
    assert seen[1].url.path == "/api/v1/analytic/statuses"


def test_errors_and_validation_are_sanitized():
    def fail(request):
        return httpx.Response(401, json={"error": "private-token"})

    with MrScraperClient("private-token", transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(AuthenticationError) as error:
            client.fetch_html("https://example.com")
    assert error.value.status_code == 401
    assert "private-token" not in str(error.value)
    assert error.value.__context__ is None

    def fail_server(request):
        return httpx.Response(500, json={"error": "private-token"})

    with MrScraperClient("private-token", transport=httpx.MockTransport(fail_server)) as client:
        with pytest.raises(APIError) as error:
            client.fetch_html("https://example.com")
    assert error.value.status_code == 500
    assert "private-token" not in str(error.value)
    assert error.value.__context__ is None

    def fail_network(request):
        raise httpx.ConnectError("private-token", request=request)

    with MrScraperClient("private-token", transport=httpx.MockTransport(fail_network)) as client:
        with pytest.raises(NetworkError) as error:
            client.fetch_html("https://example.com")
    assert "private-token" not in str(error.value)
    assert error.value.__context__ is None

    with MrScraperClient("secret", transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(ValueError):
            client.fetch_html("https://example.com", timeout=301)
        with pytest.raises(ValueError):
            client.bulk_rerun_ai_scraper("s", [])
        with pytest.raises(ValueError):
            client.get_all_results(sort_field="unknown")
        with pytest.raises(ValueError):
            client.extract_structured_data("https://example.com", "unknown")


def test_agent_tool_removes_nested_image_cookie_token_fields():
    def respond(request):
        return httpx.Response(200, json={"data": {"markdown": "Hello",
                                                  "screenshot": "base64-image",
                                                  "cookies": ["session-secret"],
                                                  "apiToken": "private-token"}})

    with MrScraperClient("private-token", transport=httpx.MockTransport(respond)) as client:
        result = make_mrscraper_tools(client)[0]("https://example.com")
    assert "Hello" in result
    assert "base64-image" not in result
    assert "session-secret" not in result
    assert "private-token" not in result
