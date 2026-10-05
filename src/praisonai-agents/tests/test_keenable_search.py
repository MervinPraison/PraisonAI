import importlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
from urllib.error import HTTPError

import pytest

web_search_module = importlib.import_module("praisonaiagents.tools.web_search")


class KeenableHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append({
            "method": self.command,
            "path": self.path,
            "body": json.loads(body) if body else None,
            "title": self.headers.get("X-Keenable-Title"),
            "api_key": self.headers.get("X-API-Key"),
            "content_type": self.headers.get("Content-Type"),
        })
        status, payload = self.server.reply
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in self.server.reply_headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(data) * self.server.drip_repeats))
        self.end_headers()
        try:
            for _ in range(self.server.drip_repeats):
                self.wfile.write(data)
                self.wfile.flush()
                if self.server.drip_repeats > 1:
                    time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # A followed 302 arrives as a GET; record it the same way so a leak would show up.
    do_GET = do_POST

    def log_message(self, format, *args):
        return


@pytest.fixture
def keenable_server(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), KeenableHandler)
    server.daemon_threads = True
    server.requests = []
    server.reply = (200, {"results": []})
    server.reply_headers = {}
    server.drip_repeats = 1
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    monkeypatch.setattr(web_search_module, "KEENABLE_SEARCH_URL", f"{base}/v1/search")
    monkeypatch.setattr(web_search_module, "KEENABLE_PUBLIC_SEARCH_URL", f"{base}/v1/search/public")
    monkeypatch.delenv("KEENABLE_API_KEY", raising=False)
    monkeypatch.delenv("WEB_SEARCH_PROVIDER", raising=False)
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_keenable_is_explicit_and_does_not_change_default_order(monkeypatch):
    default_names = [name for name, _, _ in web_search_module.SEARCH_PROVIDERS]
    selectable_names = [name for name, _, _ in web_search_module.SELECTABLE_SEARCH_PROVIDERS]
    assert "keenable" not in default_names
    assert "keenable" in selectable_names
    assert web_search_module._check_keenable() == (True, None)


def test_keenable_keyless_call_maps_results(keenable_server):
    keenable_server.reply = (200, {"results": [
        {"title": "T" * 300, "url": "https://example.com/one", "description": "", "snippet": "S" * 1500},
        {"title": "Second", "url": "https://example.com/two", "description": "", "snippet": "line one\n\nline   two"},
        {"title": "Third", "url": "https://example.com/three", "description": "", "snippet": "extra"},
    ]})

    result = web_search_module.search_web("agent frameworks", max_results=2, providers="keenable")

    request, = keenable_server.requests
    assert request["path"] == "/v1/search/public"
    assert request["title"] == web_search_module.KEENABLE_APP_TITLE
    assert request["api_key"] is None
    assert request["content_type"] == "application/json"
    assert request["body"] == {
        "query": "agent frameworks",
        "max_results": 2,
        "snippet_max_length": web_search_module.KEENABLE_MAX_SNIPPET_CHARS,
    }
    assert [r["url"] for r in result] == ["https://example.com/one", "https://example.com/two"]
    assert all(r["provider"] == "keenable" for r in result)
    assert len(result[0]["title"]) == web_search_module.KEENABLE_MAX_TITLE_CHARS
    assert result[0]["title"].endswith("…")
    assert len(result[0]["snippet"]) == web_search_module.KEENABLE_MAX_SNIPPET_CHARS
    assert result[1]["snippet"] == "line one line two"


def test_keenable_key_selects_the_authenticated_endpoint(keenable_server, monkeypatch):
    monkeypatch.setenv("KEENABLE_API_KEY", "keen_test")
    keenable_server.reply = (200, {"results": [{"title": "A", "url": "https://a.dev", "snippet": "a"}]})

    web_search_module._search_keenable("q")

    request, = keenable_server.requests
    assert request["path"] == "/v1/search"
    assert request["api_key"] == "keen_test"
    assert request["title"] == web_search_module.KEENABLE_APP_TITLE


def test_keenable_falls_back_to_description_and_skips_unusable_results(keenable_server):
    keenable_server.reply = (200, {"results": [
        "not a dict",
        {"title": "No URL", "snippet": "x"},
        {"title": "Long URL", "url": "https://a.dev/" + "x" * 3000, "snippet": "x"},
        {"title": "Described", "url": "https://b.dev", "description": "from description"},
    ]})

    result = web_search_module._search_keenable("q")

    assert result == [{"title": "Described", "url": "https://b.dev", "snippet": "from description", "provider": "keenable"}]


def test_keenable_clamps_max_results(keenable_server):
    assert web_search_module._search_keenable("q", max_results=0) == []
    assert keenable_server.requests == []

    web_search_module._search_keenable("q", max_results=500)
    assert keenable_server.requests[0]["body"]["max_results"] == web_search_module.KEENABLE_MAX_RESULTS


@pytest.mark.parametrize("payload", [None, [], {}, {"results": {}}, {"other": []}])
def test_keenable_rejects_malformed_result_shape(keenable_server, payload):
    keenable_server.reply = (200, payload)
    with pytest.raises(ValueError, match="invalid response shape"):
        web_search_module._search_keenable("q")


def test_keenable_response_limit_is_enforced(keenable_server, monkeypatch):
    monkeypatch.setattr(web_search_module, "KEENABLE_MAX_RESPONSE_BYTES", 64)
    keenable_server.reply = (200, {"results": [{"title": "x" * 200, "url": "https://a.dev", "snippet": "x"}]})
    with pytest.raises(ValueError, match="oversized"):
        web_search_module._search_keenable("q")


def test_keenable_rate_limit_moves_search_web_to_the_next_provider(keenable_server, monkeypatch):
    keenable_server.reply = (429, {"detail": "Rate limit exceeded"})
    calls = []

    def check_next():
        return True, None

    def search_next(query, max_results):
        calls.append(query)
        return [{"title": "Next", "url": "https://example.com", "snippet": "", "provider": "next"}]

    monkeypatch.setattr(
        web_search_module,
        "SELECTABLE_SEARCH_PROVIDERS",
        web_search_module.SELECTABLE_SEARCH_PROVIDERS + [("next", check_next, search_next)],
    )
    result = web_search_module.search_web("q", providers="keenable, next")

    assert len(keenable_server.requests) == 1
    assert calls == ["q"]
    assert result[0]["provider"] == "next"


def test_keenable_is_selected_by_environment_variable(keenable_server, monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", "keenable")
    keenable_server.reply = (200, {"results": [{"title": "A", "url": "https://a.dev", "snippet": "a"}]})

    result = web_search_module.search_web("q")

    assert result[0]["provider"] == "keenable"
    assert keenable_server.requests[0]["path"] == "/v1/search/public"


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_keenable_does_not_follow_redirects_with_the_key(keenable_server, monkeypatch, status):
    monkeypatch.setenv("KEENABLE_API_KEY", "keen_test")
    keenable_server.reply = (status, b"")
    keenable_server.reply_headers = {"Location": "/collect"}

    with pytest.raises(HTTPError) as excinfo:
        web_search_module._search_keenable("q")

    assert excinfo.value.code == status
    assert [r["path"] for r in keenable_server.requests] == ["/v1/search"]


def test_keenable_enforces_an_overall_deadline(keenable_server, monkeypatch):
    # Each byte arrives well inside the socket timeout, so only the overall deadline stops it.
    monkeypatch.setattr(web_search_module, "KEENABLE_SEARCH_TIMEOUT_SECONDS", 0.3)
    keenable_server.reply = (200, b" ")
    keenable_server.drip_repeats = 200

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="in time"):
        web_search_module._search_keenable("q")

    assert time.monotonic() - started < 2
