"""OpenAPI tools and URL knowledge must go through the shared SSRF guard (#5942)."""

import pytest

from praisonaiagents.tools.openapi_toolset import OpenAPIToolset


@pytest.mark.parametrize("server", ["http://127.0.0.1:9", "http://169.254.169.254", "http://0177.0.0.1"])
def test_operation_refuses_internal_server(monkeypatch, server):
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    spec = {"openapi": "3.0.0", "servers": [{"url": server}],
            "paths": {"/meta": {"get": {"operationId": "getMeta"}}}}
    tool = OpenAPIToolset(spec_dict=spec).get_tools()[0]
    assert "refusing unsafe URL" in tool()


def test_spec_url_is_checked_before_fetch(monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    with pytest.raises(ValueError, match="unsafe spec_url"):
        OpenAPIToolset(spec_url="http://169.254.169.254/openapi.json")


def test_knowledge_refuses_internal_url(monkeypatch):
    monkeypatch.delenv("ALLOW_LOCAL_CRAWL", raising=False)
    from praisonaiagents.knowledge.knowledge import Knowledge

    kb = Knowledge.__new__(Knowledge)  # the guard runs before any fetcher is touched
    with pytest.raises(ValueError, match="unsafe URL"):
        kb._process_url("http://169.254.169.254/latest/meta-data")
