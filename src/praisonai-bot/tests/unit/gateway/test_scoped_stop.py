#!/usr/bin/env python3
"""Regression tests for session-scoped stop (Issue #5129).

A gateway ``Stop`` used to cancel only the in-flight turn; queued-but-unstarted
messages in the same session were still executed afterwards. These tests pin the
scoped-stop contract:

- ``StopScope.coerce`` never escalates a malformed scope, and ``StopResult``
  serialises the reported outcome.
- ``/stop`` (``TURN``) preserves the queued backlog; ``/stop all`` / ``/cancel``
  (``SESSION``) drain it and count the cancellations.
- A session stop with no active turn still accounts for queued work.
- An unknown session id is a safe no-op.
- The dequeue-to-registration race is closed: a message pulled from the inbox
  but not yet dispatched is dropped (and counted) when a session stop lands in
  that gap, instead of running after the user cancelled it.
"""

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonaiagents.gateway.protocols import StopScope, StopResult
from praisonai_bot.gateway.server import WebSocketGateway, GatewaySession


# ---------------------------------------------------------------------------
# Core primitive: StopScope coercion + StopResult serialisation
# ---------------------------------------------------------------------------

def test_stop_scope_values():
    assert StopScope.TURN.value == "turn"
    assert StopScope.SESSION.value == "session"


@pytest.mark.parametrize(
    "value,expected",
    [
        (StopScope.SESSION, StopScope.SESSION),
        ("session", StopScope.SESSION),
        ("SESSION", StopScope.SESSION),
        (" session ", StopScope.SESSION),
        ("turn", StopScope.TURN),
        (True, StopScope.SESSION),
        (False, StopScope.TURN),
        (None, StopScope.TURN),
        ("nonsense", StopScope.TURN),   # malformed never escalates
        (object(), StopScope.TURN),     # unparseable never escalates
    ],
)
def test_stop_scope_coerce(value, expected):
    assert StopScope.coerce(value) is expected


def test_stop_scope_coerce_default_never_escalates():
    # A malformed value falls back to the caller's default, not SESSION.
    assert StopScope.coerce("bogus", default=StopScope.TURN) is StopScope.TURN


def test_stop_result_to_dict_roundtrip():
    res = StopResult(scope=StopScope.SESSION, turn_aborted=True, pending_cancelled=3)
    assert res.to_dict() == {
        "scope": "session",
        "turn_aborted": True,
        "pending_cancelled": 3,
    }
    turn = StopResult(scope=StopScope.TURN, turn_aborted=False)
    assert turn.to_dict()["pending_cancelled"] == 0


# ---------------------------------------------------------------------------
# Drain semantics on the bot gateway
# ---------------------------------------------------------------------------

def _register_session(gw: WebSocketGateway, sid="sess-1", queued=()):
    session = GatewaySession(_session_id=sid, _agent_id="agent-1")
    for msg in queued:
        session._inbox.put_nowait(msg)
    gw._sessions[sid] = session
    return session


def test_turn_scope_preserves_backlog():
    async def go():
        gw = WebSocketGateway()
        session = _register_session(gw, queued=["a", "b", "c"])
        result = gw._abort_session(session.session_id, scope=StopScope.TURN)
        assert result.scope is StopScope.TURN
        assert result.pending_cancelled == 0
        # Backlog is untouched under a turn-scoped stop.
        assert session._inbox.qsize() == 3

    asyncio.run(go())


def test_session_scope_drains_and_counts():
    async def go():
        gw = WebSocketGateway()
        session = _register_session(gw, queued=["a", "b", "c"])
        result = gw._abort_session(session.session_id, scope=StopScope.SESSION)
        assert result.scope is StopScope.SESSION
        assert result.pending_cancelled == 3
        assert session._inbox.empty()

    asyncio.run(go())


def test_session_scope_without_active_turn_still_accounts_queue():
    async def go():
        gw = WebSocketGateway()
        session = _register_session(gw, queued=["only"])
        result = gw._abort_session(session.session_id, scope=StopScope.SESSION)
        # No active turn, but the queued work is still counted and drained.
        assert result.turn_aborted is False
        assert result.pending_cancelled == 1
        assert session._inbox.empty()

    asyncio.run(go())


def test_unknown_session_is_safe_noop():
    async def go():
        gw = WebSocketGateway()
        result = gw._abort_session("does-not-exist", scope=StopScope.SESSION)
        assert result.turn_aborted is False
        assert result.pending_cancelled == 0

    asyncio.run(go())


# ---------------------------------------------------------------------------
# Dequeue-to-registration race (the P1 finding)
# ---------------------------------------------------------------------------

def test_session_stop_counts_inflight_unstarted_message():
    """A message dequeued but not yet dispatched is counted and epoch-bumped."""
    async def go():
        gw = WebSocketGateway()
        session = _register_session(gw, queued=[])
        # Simulate the worker having pulled the message off the inbox but not yet
        # registered/dispatched it (the race window).
        session._inflight_unstarted = True
        before_epoch = session._stop_epoch

        result = gw._abort_session(session.session_id, scope=StopScope.SESSION)

        # The in-flight-unstarted message is counted...
        assert result.pending_cancelled == 1
        # ...and the epoch advanced so the worker drops it before dispatch.
        assert session._stop_epoch == before_epoch + 1

    asyncio.run(go())


def test_turn_scope_does_not_bump_epoch_or_count_inflight():
    async def go():
        gw = WebSocketGateway()
        session = _register_session(gw, queued=["queued"])
        session._inflight_unstarted = True
        before_epoch = session._stop_epoch

        result = gw._abort_session(session.session_id, scope=StopScope.TURN)

        # Turn scope is byte-for-byte back-compat: no drain, no count, no bump.
        assert result.pending_cancelled == 0
        assert session._stop_epoch == before_epoch
        assert session._inbox.qsize() == 1

    asyncio.run(go())
