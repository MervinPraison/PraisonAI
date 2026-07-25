#!/usr/bin/env python3
"""Tests for restart continuation of interrupted in-flight turns (Issue #3379).

Verifies that a turn left in-flight when the gateway restarts is re-driven on
the next boot and that the originating channel is proactively (and idempotently)
notified — independent of any client reconnect.
"""

import asyncio

import pytest

from praisonai_bot.gateway.server import GatewaySession, WebSocketGateway


def test_channel_target_round_trips_through_serialization():
    """``channel_target`` survives to_dict/from_dict so boot resume can notify."""
    session = GatewaySession(
        _session_id="s1",
        _agent_id="agent-1",
        _client_id=None,
    )
    session.set_channel_target("telegram:12345")
    session.mark_executing(True)

    data = session.to_dict()
    assert data["channel_target"] == "telegram:12345"

    restored = GatewaySession.from_dict(data)
    assert restored.channel_target == "telegram:12345"
    assert restored._is_executing is True


def test_channel_target_defaults_none_for_legacy_data():
    """Sessions persisted before this field deserialize with no target."""
    legacy = {
        "session_id": "s2",
        "agent_id": "agent-1",
        "is_executing": True,
        "pending_inbox": [],
    }
    restored = GatewaySession.from_dict(legacy)
    assert restored.channel_target is None


class _FakeStore:
    """Minimal session store exposing the two boot-scan methods we use."""

    def __init__(self, sessions):
        # sessions: {session_id: session_data_dict}
        self._sessions = sessions

    def list_sessions(self, limit: int = 50):
        return [{"session_id": sid} for sid in self._sessions]

    def get_session(self, session_id):
        data = self._sessions.get(session_id)

        class _Msg:
            def __init__(self, role, metadata):
                self.role = role
                self.metadata = metadata

        class _SessionObj:
            def __init__(self, messages):
                self.messages = messages

        if data is None:
            return _SessionObj([])
        return _SessionObj([_Msg("system", {"session_data": data})])


def _make_gateway_with_store(store):
    gateway = WebSocketGateway(port=0)
    gateway._session_store = store
    return gateway


def test_resume_notifies_channel_for_interrupted_turn():
    """An interrupted channel turn triggers exactly one idempotent notice."""
    session = GatewaySession(_session_id="s3", _agent_id="agent-1")
    session.set_channel_target("telegram:999")
    session.mark_executing(True)
    data = session.to_dict()

    gateway = _make_gateway_with_store(_FakeStore({"s3": data}))

    sent = []

    async def _fake_notice(channel_target, text, session_id, run_epoch):
        sent.append((channel_target, text, session_id, run_epoch))
        return True

    gateway._deliver_restart_notice = _fake_notice

    resumed = asyncio.run(gateway._resume_interrupted_turns())

    assert resumed == 1
    assert len(sent) == 1
    assert sent[0][0] == "telegram:999"
    assert sent[0][2] == "s3"


def test_resume_skips_sessions_without_channel_target():
    """Direct-client interrupted sessions are not channel-notified."""
    session = GatewaySession(_session_id="s4", _agent_id="agent-1")
    session.mark_executing(True)  # interrupted but no channel origin
    data = session.to_dict()

    gateway = _make_gateway_with_store(_FakeStore({"s4": data}))

    sent = []

    async def _fake_notice(*args):
        sent.append(args)
        return True

    gateway._deliver_restart_notice = _fake_notice

    resumed = asyncio.run(gateway._resume_interrupted_turns())

    assert resumed == 0
    assert sent == []


def test_resume_skips_completed_sessions():
    """A session with no in-flight work is left untouched."""
    session = GatewaySession(_session_id="s5", _agent_id="agent-1")
    session.set_channel_target("telegram:1")
    session.mark_executing(False)  # not executing, empty inbox
    data = session.to_dict()

    gateway = _make_gateway_with_store(_FakeStore({"s5": data}))

    sent = []

    async def _fake_notice(*args):
        sent.append(args)
        return True

    gateway._deliver_restart_notice = _fake_notice

    resumed = asyncio.run(gateway._resume_interrupted_turns())

    assert resumed == 0
    assert sent == []


def test_resume_is_noop_without_store():
    """No durable store => no-op, no crash."""
    gateway = WebSocketGateway(port=0)
    gateway._session_store = None
    resumed = asyncio.run(gateway._resume_interrupted_turns())
    assert resumed == 0


def test_restart_notice_idempotency_key_scopes_session_and_epoch():
    """The notice idempotency key is keyed on (session_id, run_epoch)."""
    gateway = WebSocketGateway(port=0)

    captured = {}

    class _FakeRouter:
        async def deliver(self, route, text, idempotency_key=None):
            captured["route"] = route
            captured["idem"] = idempotency_key
            return True

    gateway._delivery_router = _FakeRouter()

    delivered = asyncio.run(
        gateway._deliver_restart_notice("telegram:42", "hi", "sess-7", 3)
    )

    assert delivered is True
    assert captured["route"] == "telegram:42"
    assert captured["idem"] == "restart:sess-7:3"


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(pytest.main([__file__, "-v"]))
