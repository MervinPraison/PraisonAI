"""Headless and concurrent OAuth callback handling (issue #6179)."""

import threading
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.fixture
def provider_env(tmp_path, monkeypatch):
    from praisonaiagents.mcp import oauth_provider
    from praisonaiagents.mcp.mcp_auth_storage import MCPAuthStorage

    started = []

    class FakeServer:
        def serve_forever(self):
            pass

        def shutdown(self):
            pass

        def server_close(self):
            pass

    def fake_make(handler, port):
        started.append(handler)
        return FakeServer()

    monkeypatch.setattr(oauth_provider, "_make_callback_server", fake_make)
    monkeypatch.setattr(oauth_provider, "_paste_states", set())
    monkeypatch.setattr(oauth_provider, "_paste_reader", None)
    monkeypatch.setattr(
        oauth_provider.MCPOAuthProvider,
        "_exchange_code",
        lambda self, m, c, code, v, timeout: {"access_token": f"tok-{code}"},
    )
    storage = MCPAuthStorage(filepath=str(tmp_path / "auth.json"))
    return oauth_provider, storage, started


METADATA = {
    "authorization_endpoint": "https://auth.example.com/authorize",
    "token_endpoint": "https://auth.example.com/token",
}


def _state_of(url):
    return parse_qs(urlparse(url).query)["state"][0]


def test_concurrent_flows_share_one_callback_server(provider_env, monkeypatch):
    oauth_provider, storage, started = provider_env
    urls = []
    both_opened = threading.Barrier(2)

    def fake_open(url):
        urls.append((threading.current_thread().name, url))
        both_opened.wait(timeout=5)
        return True

    monkeypatch.setattr(oauth_provider.webbrowser, "open", fake_open)

    results = {}

    def run(name):
        p = oauth_provider.MCPOAuthProvider(name, f"https://{name}.example/mcp", storage=storage)
        results[name] = p._run_pkce_flow(METADATA, {"client_id": "c"}, None, timeout=5)

    threads = [threading.Thread(target=run, args=(n,), name=n) for n in ("a", "b")]
    for t in threads:
        t.start()
    for _ in range(100):
        if len(urls) == 2:
            break
        threading.Event().wait(0.05)
    assert len(started) == 1  # single bind, no port collision
    handler = started[0]
    for name, url in urls:
        handler.receive_callback(_state_of(url), f"code-{name}")
    for t in threads:
        t.join(timeout=5)

    # Each flow must get the code sent for *its* state, not just any code.
    assert results == {"a": "tok-code-a", "b": "tok-code-b"}
    assert oauth_provider._callback_server is None  # released after last flow


def test_headless_prints_url_and_accepts_pasted_redirect(provider_env, monkeypatch, capsys):
    oauth_provider, storage, _ = provider_env
    monkeypatch.setattr(oauth_provider.webbrowser, "open", lambda url: False)

    class TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(oauth_provider.sys, "stdin", TTY())
    printed = threading.Event()
    real_print = print

    def fake_input(prompt=""):
        printed.wait(timeout=5)
        err = capsys.readouterr().err
        auth_url = err.split("\n")[1].strip()
        return f"http://127.0.0.1:19876/mcp/oauth/callback?code=xyz&state={_state_of(auth_url)}"

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr(
        "builtins.print",
        lambda *a, **k: (real_print(*a, **k), printed.set()),
    )

    p = oauth_provider.MCPOAuthProvider("n", "https://n.example/mcp", storage=storage)
    assert p._run_pkce_flow(METADATA, {"client_id": "c"}, None, timeout=5) == "tok-xyz"


def test_concurrent_headless_flows_share_one_paste_reader(provider_env, monkeypatch):
    oauth_provider, storage, _ = provider_env
    urls = []
    both_opened = threading.Barrier(2)

    def fake_open(url):
        urls.append((threading.current_thread().name, url))
        both_opened.wait(timeout=5)
        return False

    class TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(oauth_provider.webbrowser, "open", fake_open)
    monkeypatch.setattr(oauth_provider.sys, "stdin", TTY())

    readers = []
    pasted = []

    def fake_input(prompt=""):
        readers.append(threading.current_thread())
        while len(urls) < 2 or len(oauth_provider._paste_states) + len(pasted) < 2:
            threading.Event().wait(0.01)
        # Paste in the reverse order the flows started: B's redirect first.
        name, url = sorted(urls, reverse=True)[len(pasted)]
        pasted.append(name)
        return f"http://127.0.0.1:19876/mcp/oauth/callback?code=c-{name}&state={_state_of(url)}"

    monkeypatch.setattr("builtins.input", fake_input)

    results = {}

    def run(name):
        p = oauth_provider.MCPOAuthProvider(name, f"https://{name}.example/mcp", storage=storage)
        results[name] = p._run_pkce_flow(METADATA, {"client_id": "c"}, None, timeout=5)

    threads = [threading.Thread(target=run, args=(n,), name=n) for n in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert results == {"a": "tok-c-a", "b": "tok-c-b"}
    assert len(set(readers)) == 1  # one terminal reader, not one per flow
    assert oauth_provider._paste_reader is None  # stops once no flow is waiting


def test_parse_redirect():
    from praisonaiagents.mcp.oauth_provider import _parse_redirect

    assert _parse_redirect(" http://127.0.0.1:19876/cb?state=s&code=c\n") == ("s", "c")
    assert _parse_redirect("garbage") == ("", "")
