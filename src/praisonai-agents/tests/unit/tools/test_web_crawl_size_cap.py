"""web_crawl's httpx path must not buffer bodies past its byte cap (#5969)."""

import pytest

from praisonaiagents.tools import web_crawl_tools as w


@pytest.fixture
def mock_client(monkeypatch):
    httpx = pytest.importorskip("httpx")

    def install(handler):
        real_client = httpx.Client

        def client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return real_client(*args, **kwargs)

        monkeypatch.setattr(httpx, "Client", client)
        # Hermetic DNS: example.com answers a public address.
        monkeypatch.setattr(
            "socket.getaddrinfo",
            lambda host, port=0, *a, **k: [(2, 1, 6, "", ("93.184.216.34", port or 0))],
        )

    return install


def test_oversized_body_is_read_only_up_to_cap(mock_client):
    import httpx

    sent = []
    chunk = b"a" * (1024 * 1024)

    def body():
        for _ in range(100):  # 100 MB if fully consumed
            sent.append(len(chunk))
            yield chunk

    mock_client(lambda request: httpx.Response(200, content=body(), headers={"Content-Type": "text/html"}))

    result = w._crawl_with_httpx(["http://example.com/"])[0]

    assert "error" not in result
    assert len(result["content"]) == 50000
    assert sum(sent) <= w._MAX_CRAWL_BYTES + len(chunk)


def test_redirect_is_followed_and_small_page_unchanged(mock_client):
    import httpx

    def handler(request):
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/page"})
        return httpx.Response(200, text="<html><title>T</title><h1>Hi</h1></html>")

    mock_client(handler)

    result = w._crawl_with_httpx(["http://example.com/start"])[0]

    assert result["title"] == "T"
    assert result["content"] == "# Hi"

