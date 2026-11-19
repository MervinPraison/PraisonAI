"""Remote browser server mode is token-gated; loopback clients are unchanged."""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from praisonai_browser.server import BrowserServer

EXT = "chrome-extension://" + "a" * 32


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("PRAISONAI_BROWSER_TOKEN", raising=False)
    monkeypatch.setenv("PRAISONAI_BROWSER_ALLOW_REMOTE", "true")


def test_remote_bind_without_token_refuses():
    with pytest.raises(ValueError, match="PRAISONAI_BROWSER_TOKEN"):
        BrowserServer(host="0.0.0.0")


def test_remote_client_with_forged_origin_but_no_token_is_closed(monkeypatch):
    monkeypatch.setenv("PRAISONAI_BROWSER_TOKEN", "t-1")
    client = TestClient(BrowserServer(host="0.0.0.0")._get_app())  # peer "testclient" = remote
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"Origin": EXT}) as ws:
            ws.receive_text()


def test_remote_client_with_token_is_accepted(monkeypatch):
    monkeypatch.setenv("PRAISONAI_BROWSER_TOKEN", "t-1")
    client = TestClient(BrowserServer(host="0.0.0.0")._get_app())
    with client.websocket_connect("/ws?token=t-1", headers={"Origin": EXT}):
        pass


def test_loopback_server_needs_no_token():
    assert BrowserServer(host="127.0.0.1")._token is None
