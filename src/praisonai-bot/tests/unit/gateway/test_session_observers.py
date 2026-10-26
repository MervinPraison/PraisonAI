"""Shared-session observers on the gateway server (Issue #5997).

The wrapper gateway implements core's ``SessionObserverProtocol`` honouring
``SessionVisibility`` / ``SessionSharingRole``: private sessions stay 1:1,
attached observers receive the live turn stream gated by their scopes, and a
member/viewer leaving never closes the owner's session.
"""

import asyncio

import pytest

from praisonaiagents.gateway import GatewayConfig
from praisonaiagents.gateway.protocols import (
    SessionObserverProtocol,
    SessionSharingRole,
)
from praisonai_bot.gateway.server import WebSocketGateway


class _WS:
    def __init__(self):
        self.sent = []

    async def send_json(self, data):
        self.sent.append(data)

    async def close(self, code=None, reason=None):
        pass


class _EmitterAgent:
    def __init__(self):
        from praisonaiagents.streaming.events import StreamEventEmitter

        self.stream_emitter = StreamEventEmitter()

    async def achat(self, content):
        from praisonaiagents.streaming.events import StreamEvent, StreamEventType

        self.stream_emitter.emit(
            StreamEvent(type=StreamEventType.DELTA_TEXT, content="tok")
        )
        await asyncio.sleep(0)
        return f"echo:{content}"


def _gateway():
    return WebSocketGateway(config=GatewayConfig(auth_token="tmp"))


def _client(gw, cid, scopes=None):
    # Direct registration (no bounded conn) so sends land synchronously.
    ws = _WS()
    gw._clients[cid] = ws
    if scopes is not None:
        gw._client_scopes[cid] = scopes
    return ws


def _owned(gw, visibility=None):
    session = gw.create_session("agent", client_id="owner", visibility=visibility)
    gw._client_sessions["owner"] = session.session_id
    return session


def test_gateway_satisfies_observer_protocol():
    assert isinstance(_gateway(), SessionObserverProtocol)


def test_private_session_refuses_observers_by_default():
    gw = _gateway()
    session = _owned(gw)
    assert session._visibility == "private"
    with pytest.raises(PermissionError):
        gw.attach(session.session_id, "bob")
    assert gw.observers(session.session_id) == [("owner", SessionSharingRole.OWNER)]


def test_read_only_admits_viewers_only():
    gw = _gateway()
    session = _owned(gw, visibility="read_only")
    with pytest.raises(PermissionError):
        gw.attach(session.session_id, "ann", role="member")
    gw.attach(session.session_id, "bob", role="viewer")
    assert ("bob", SessionSharingRole.VIEWER) in gw.observers(session.session_id)
    # A viewer is not bound to the session, so it cannot send.
    assert "bob" not in gw._client_sessions


def test_shared_attach_detach_roster():
    gw = _gateway()
    session = _owned(gw, visibility="shared")
    sid = session.session_id
    gw.attach(sid, "bob", role="viewer")
    gw.attach(sid, "ann", role="member")
    assert gw.observers(sid) == [
        ("owner", SessionSharingRole.OWNER),
        ("bob", SessionSharingRole.VIEWER),
        ("ann", SessionSharingRole.MEMBER),
    ]
    # A member co-drives through the normal ``message`` path.
    assert gw._client_sessions["ann"] == sid
    with pytest.raises(ValueError):
        gw.attach(sid, "owner", role="member")

    gw.detach(sid, "ann")
    assert "ann" not in gw._client_sessions
    assert gw.observers(sid) == [
        ("owner", SessionSharingRole.OWNER),
        ("bob", SessionSharingRole.VIEWER),
    ]


def test_visibility_survives_persistence_round_trip():
    gw = _gateway()
    session = _owned(gw, visibility="shared")
    restored = type(session).from_dict(session.to_dict())
    assert restored._visibility == "shared"


def test_observer_leaving_does_not_close_owner_session():
    gw = _gateway()
    session = _owned(gw, visibility="shared")
    sid = session.session_id
    gw.attach(sid, "ann", role="member")
    gw.attach(sid, "bob", role="viewer")

    assert gw._release_client_session("ann") == sid
    gw._release_client_session("bob")
    assert gw.get_session(sid) is session
    assert gw.observers(sid) == [("owner", SessionSharingRole.OWNER)]

    # The owner leaving closes the session and drops any remaining observers.
    gw.attach(sid, "ann", role="member")
    gw._release_client_session("owner")
    assert gw.get_session(sid) is None
    assert "ann" not in gw._client_sessions
    assert sid not in gw._session_observers


def test_live_turn_fans_out_to_observers_gated_by_scope():
    async def _run():
        gw = _gateway()
        owner_ws = _client(gw, "owner")
        viewer_ws = _client(gw, "bob", scopes=["read"])
        blind_ws = _client(gw, "eve", scopes=["write"])  # no READ -> nothing
        session = _owned(gw, visibility="shared")
        gw.attach(session.session_id, "bob", role="viewer")
        gw.attach(session.session_id, "eve", role="member")

        agent = _EmitterAgent()
        session.mark_executing(True)
        await session.queue_message("hi")
        await gw._run_session_queue(session, agent, "owner")
        return owner_ws, viewer_ws, blind_ws

    owner_ws, viewer_ws, blind_ws = asyncio.run(_run())

    def _shape(ws):
        return [(f["type"], f.get("content") or f.get("data", {}).get("content")) for f in ws.sent]

    expected_tail = ("response", "echo:hi")
    assert ("token_stream", "tok") in _shape(owner_ws)
    assert _shape(owner_ws)[-1] == expected_tail
    assert ("token_stream", "tok") in _shape(viewer_ws)
    assert _shape(viewer_ws)[-1] == expected_tail
    assert blind_ws.sent == []
