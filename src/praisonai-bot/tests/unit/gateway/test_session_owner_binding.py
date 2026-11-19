"""A gateway session is bound to the operator credential that created it.

Under an operator scope policy (``auth_scopes``) each token is a separate
operator. ``hello`` / ``join`` with a ``session_id`` then resume the session
only for the same credential; another credential gets the same refusal as a
wrong agent, and the session keeps its client. With no scope policy every
authenticated client is the one operator, so nothing changes.
"""

import asyncio
import hashlib

import pytest

from praisonaiagents.gateway import GatewayConfig
from praisonai_bot.gateway.server import GatewaySession, WebSocketGateway


class _WS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=None, reason=None):
        pass


def _principal(token):
    return "token:" + hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


@pytest.fixture(autouse=True)
def _isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)


POLICY = {"tok-owner": ["admin"], "tok-reader": ["read", "write"]}


def _gateway():
    gw = WebSocketGateway(config=GatewayConfig(auth_token="tok-owner", auth_scopes=dict(POLICY)))
    gw._agents["assistant"] = object()
    return gw


def _connect(gw, cid, token):
    ws = _WS()
    gw._clients[cid] = ws
    gw._client_principals[cid] = _principal(token) if token else None
    return ws


def _hello(gw, cid, frame, session_id=None):
    msg = {"type": frame, "agent_id": "assistant"}
    if session_id:
        msg["session_id"] = session_id
    asyncio.run(gw._handle_client_message(cid, msg))
    return gw._client_sessions.get(cid)


@pytest.mark.parametrize("frame", ["hello", "join"])
def test_other_credential_cannot_resume_session(frame):
    gw = _gateway()
    _connect(gw, "victim", "tok-owner")
    sid = _hello(gw, "victim", frame)
    assert sid and gw.get_session(sid)._owner == _principal("tok-owner")

    ws = _connect(gw, "other", "tok-reader")
    assert _hello(gw, "other", frame, session_id=sid) is None
    assert gw.get_session(sid).client_id == "victim"
    assert gw._client_sessions["victim"] == sid
    assert any("does not belong" in str(m.get("message", "")) for m in ws.sent)


@pytest.mark.parametrize("frame", ["hello", "join"])
def test_same_credential_resumes_after_reconnect(frame):
    gw = _gateway()
    _connect(gw, "first", "tok-owner")
    sid = _hello(gw, "first", frame)
    _connect(gw, "second", "tok-owner")
    assert _hello(gw, "second", frame, session_id=sid) == sid


def test_unowned_session_is_claimed_by_first_resumer():
    gw = _gateway()
    legacy = gw.create_session("assistant", None, "legacy-sid")
    assert legacy._owner is None
    _connect(gw, "c1", "tok-owner")
    assert _hello(gw, "c1", "hello", session_id="legacy-sid") == "legacy-sid"
    assert legacy._owner == _principal("tok-owner")
    _connect(gw, "c2", "tok-reader")
    assert _hello(gw, "c2", "hello", session_id="legacy-sid") is None


def test_without_scope_policy_nothing_changes():
    gw = WebSocketGateway(config=GatewayConfig(auth_token="tok-owner"))
    gw._agents["assistant"] = object()
    _connect(gw, "a", None)
    sid = _hello(gw, "a", "hello")
    _connect(gw, "b", None)
    assert _hello(gw, "b", "hello", session_id=sid) == sid


def test_owner_survives_persistence():
    session = GatewaySession(_session_id="s1", _agent_id="assistant")
    session._owner = _principal("tok-owner")
    restored = GatewaySession.from_dict(session.to_dict())
    assert restored._owner == _principal("tok-owner")


def test_api_session_is_owned_by_the_api_token():
    from praisonai_bot.gateway.api_endpoints import GatewayApiEndpoints

    gw = _gateway()
    api = GatewayApiEndpoints(gw)
    token = api._rate_key_var.set(_principal("tok-owner"))
    try:
        session = api._session_for("assistant", "token:tok-owner")
    finally:
        api._rate_key_var.reset(token)
    assert session._owner == _principal("tok-owner")
    _connect(gw, "intruder", "tok-reader")
    assert _hello(gw, "intruder", "hello", session_id=session.session_id) is None


def test_websocket_connection_binds_its_credential(monkeypatch, tmp_path):
    """End to end: two credentials over /ws; the second cannot take the session."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    pytest.importorskip("itsdangerous")
    from starlette.testclient import TestClient
    from praisonai_bot.gateway.cookie_auth import CookieAuthManager

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("GATEWAY_AUTH_TOKEN", raising=False)
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.check_port_available", lambda *a: (True, None))
    lock = SimpleNamespace(acquire_lock=Mock(return_value=True), release_lock=Mock())
    monkeypatch.setattr("praisonai_bot.gateway.port_utils.GatewayPIDLock", lambda **kw: lock)
    server = SimpleNamespace(serve=AsyncMock(), should_exit=False)

    def capture(config):
        server.app = config.app
        return server

    monkeypatch.setattr("uvicorn.Server", capture)
    owner = "tok-owner-0123456789abcdef"
    cookie = CookieAuthManager(secret_key=owner).create_session(user_id="second-operator")
    gw = WebSocketGateway(config=GatewayConfig(
        auth_token=owner, auth_scopes={owner: ["admin"], cookie: ["read", "write"]},
    ))
    gw._agents["assistant"] = object()
    asyncio.run(gw.start())

    with TestClient(server.app, base_url="http://127.0.0.1:8765") as client:
        with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {owner}"}) as a:
            a.send_json({"type": "hello", "agent_id": "assistant"})
            sid = a.receive_json()["session_id"]
            with client.websocket_connect(
                "/ws", headers={"Cookie": f"praisonai_session={cookie}"}
            ) as b:
                b.send_json({"type": "hello", "agent_id": "assistant", "session_id": sid})
                reply = b.receive_json()
    assert reply.get("type") != "hello_ok", reply
    assert "does not belong" in reply.get("message", "")
