"""The HTTP API keeps a bounded number of live sessions.

``/v1/*`` keys a session on the client's ``X-Session-Id``, so a caller can mint
any number of them. Past the cap the oldest API session is closed (it stays
resumable from the session store) instead of living in memory forever.
"""

import pytest

from praisonaiagents.gateway import GatewayConfig
from praisonai_bot.gateway.api_endpoints import GatewayApiEndpoints
from praisonai_bot.gateway.server import WebSocketGateway


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)


def _api(cap):
    gw = WebSocketGateway(config=GatewayConfig(auth_token="tok"))
    gw._agents["assistant"] = object()
    api = GatewayApiEndpoints(gw)
    api._api_sessions.max_items = cap
    return gw, api


def _live_api_sessions(gw):
    return [sid for sid in gw._sessions if sid.startswith("api:")]


def test_rotating_session_ids_stay_bounded():
    gw, api = _api(cap=3)
    for i in range(20):
        api._session_for("assistant", f"s{i}")
    live = _live_api_sessions(gw)
    assert len(live) == 3
    assert live == ["api:s17:assistant", "api:s18:assistant", "api:s19:assistant"]


def test_reusing_a_session_keeps_it_live():
    gw, api = _api(cap=2)
    api._session_for("assistant", "keep")
    api._session_for("assistant", "a")
    api._session_for("assistant", "keep")  # most recent again
    api._session_for("assistant", "b")
    assert sorted(_live_api_sessions(gw)) == ["api:b:assistant", "api:keep:assistant"]


def test_websocket_sessions_are_not_counted():
    gw, api = _api(cap=1)
    gw.create_session("assistant", "client-1", "ws-session")
    api._session_for("assistant", "x")
    api._session_for("assistant", "y")
    assert "ws-session" in gw._sessions
