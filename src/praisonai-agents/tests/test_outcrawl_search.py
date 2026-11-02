import importlib

import pytest

pytest.importorskip("requests")

web_search_module = importlib.import_module("praisonaiagents.tools.web_search")


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} Client Error")

    def json(self):
        return self._payload


def _fake_post(observed, payload, status_code=200):
    def post(url, headers=None, json=None, timeout=None):
        observed.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return FakeResponse(payload, status_code)

    return post


def test_outcrawl_is_a_keyed_default_provider(monkeypatch):
    default_names = [name for name, _, _ in web_search_module.SEARCH_PROVIDERS]
    assert "outcrawl" in default_names
    assert default_names.index("outcrawl") < default_names.index("duckduckgo")

    monkeypatch.delenv("OUTCRAWL_API_KEY", raising=False)
    assert web_search_module._check_outcrawl() == (False, "OUTCRAWL_API_KEY not set")
    monkeypatch.setenv("OUTCRAWL_API_KEY", "ock_test.secret")
    assert web_search_module._check_outcrawl() == (True, None)

    providers = {p["name"]: p for p in web_search_module.get_available_providers()}
    assert providers["outcrawl"]["available"] is True


def test_outcrawl_maps_hits_and_sends_bearer_key(monkeypatch):
    import requests

    observed = []
    monkeypatch.setenv("OUTCRAWL_API_KEY", "ock_test.secret")
    monkeypatch.setattr(requests, "post", _fake_post(observed, {
        "hits": [
            {"url": "https://example.com/one", "title": "One", "snippet": "First", "rank": 1},
            {"url": "https://example.com/two", "title": None, "snippet": "Second", "rank": 2},
            {"url": "https://example.com/three", "title": "Three", "snippet": "Third", "rank": 3},
        ],
        "usage": {"credits": "1.5"},
    }))

    result = web_search_module.search_web("agent frameworks", max_results=2, providers="outcrawl")

    assert observed[0]["url"] == "https://api.outcrawl.ai/v1/search"
    assert observed[0]["headers"]["Authorization"] == "Bearer ock_test.secret"
    assert observed[0]["json"] == {"query": "agent frameworks", "limit": 2}
    assert result == [
        {"title": "One", "url": "https://example.com/one", "snippet": "First", "provider": "outcrawl"},
        {"title": "", "url": "https://example.com/two", "snippet": "Second", "provider": "outcrawl"},
    ]


def test_outcrawl_clamps_limit_to_api_maximum(monkeypatch):
    import requests

    observed = []
    monkeypatch.setenv("OUTCRAWL_API_KEY", "ock_test.secret")
    monkeypatch.setattr(requests, "post", _fake_post(observed, {"hits": [{"url": "https://example.com", "title": "T", "snippet": "S"}]}))

    web_search_module._search_outcrawl("q", max_results=50)

    assert observed[0]["json"]["limit"] == web_search_module.OUTCRAWL_MAX_RESULTS


def test_outcrawl_http_error_falls_back_to_next_provider(monkeypatch):
    import requests

    monkeypatch.setenv("OUTCRAWL_API_KEY", "ock_bad.secret")
    monkeypatch.setattr(requests, "post", _fake_post([], {"error": "invalid api key"}, status_code=401))

    def check_next():
        return True, None

    def search_next(query, max_results):
        return [{"title": "Next", "url": "https://next.example.com", "snippet": "", "provider": "next"}]

    monkeypatch.setattr(web_search_module, "SELECTABLE_SEARCH_PROVIDERS", web_search_module.SELECTABLE_SEARCH_PROVIDERS + [("next", check_next, search_next)])
    result = web_search_module.search_web("q", providers=["outcrawl", "next"])

    assert result[0]["provider"] == "next"


def test_outcrawl_without_key_reports_error(monkeypatch):
    monkeypatch.delenv("OUTCRAWL_API_KEY", raising=False)

    result = web_search_module.search_web("q", providers="outcrawl")

    assert "error" in result[0]
    assert "outcrawl: OUTCRAWL_API_KEY not set" in result[0]["error"]
