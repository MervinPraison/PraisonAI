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


def test_headless_prints_url_and_never_reads_stdin(provider_env, monkeypatch, capsys):
    """Headless consent completes via the loopback callback; host stdin is untouched."""
    oauth_provider, storage, started = provider_env
    monkeypatch.setattr(oauth_provider.webbrowser, "open", lambda url: False)

    def no_input(prompt=""):
        raise AssertionError("library must not read the host's stdin")

    monkeypatch.setattr("builtins.input", no_input)

    def deliver():
        # Simulates an SSH-forwarded browser or `curl <redirect>` on the host.
        for _ in range(100):
            err = capsys.readouterr().err
            if "Open this URL" in err:
                auth_url = err.split("\n")[1].strip()
                started[0].receive_callback(_state_of(auth_url), "xyz")
                return
            threading.Event().wait(0.05)

    t = threading.Thread(target=deliver)
    t.start()
    p = oauth_provider.MCPOAuthProvider("n", "https://n.example/mcp", storage=storage)
    assert p._run_pkce_flow(METADATA, {"client_id": "c"}, None, timeout=5) == "tok-xyz"
    t.join(timeout=5)
    assert oauth_provider._callback_server is None
