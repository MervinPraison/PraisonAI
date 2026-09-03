#!/usr/bin/env python3
"""Tests for wiring the per-session turn-execution seam into the gateway (#4766).

The core seam (``TurnExecutorProtocol`` / ``InProcessTurnExecutor`` /
``TurnPlacement`` / ``WorkerWedgedError``) shipped and was unit-tested in
isolation, but nothing in the running gateway referenced it. These tests cover
``WebSocketGateway`` resolving ``GatewayConfig.executor`` and routing
``_drive_turn`` through ``place`` → ``execute_turn``, tearing down only the
offending session's worker on ``WorkerWedgedError`` instead of exiting the
whole process.
"""

import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai"))
sys.path.insert(0, str(REPO_ROOT / "src" / "praisonai-agents"))

from praisonaiagents.gateway import (
    GatewayConfig,
    InProcessTurnExecutor,
    TurnPlacement,
    WorkerWedgedError,
)
from praisonai_bot.gateway.server import WebSocketGateway


class _Agent:
    """Minimal async agent whose turn returns a fixed reply."""

    def __init__(self, reply="ok"):
        self._reply = reply

    async def arun(self, content, cancel_token=None):
        return f"{self._reply}:{content}"


def _session(sid="sess-1"):
    return types.SimpleNamespace(session_id=sid)


def test_executor_defaults_to_inprocess():
    gw = WebSocketGateway()
    assert isinstance(gw._executor, InProcessTurnExecutor)


def test_explicit_executor_is_resolved():
    ex = InProcessTurnExecutor()
    gw = WebSocketGateway(config=GatewayConfig(executor=ex))
    assert gw._executor is ex


@pytest.mark.asyncio
async def test_drive_turn_routes_through_executor():
    """The turn must be dispatched via the executor's ``place``/``execute_turn``,
    not run directly on the loop as before."""

    calls = {"place": 0, "execute": 0}

    class _RecordingExecutor:
        async def place(self, session_id):
            calls["place"] += 1
            return TurnPlacement(session_id=session_id, worker_id="w", epoch=0)

        async def execute_turn(self, placement, turn, *, cancel_token=None, limits=None):
            calls["execute"] += 1
            assert isinstance(placement, TurnPlacement)
            return await turn()

        async def teardown(self, placement, *, reason):
            return None

    gw = WebSocketGateway(config=GatewayConfig(executor=_RecordingExecutor()))
    from praisonaiagents.agent.interrupt import InterruptController

    result = await gw._drive_turn(
        _session(), _Agent("hi"), "yo", InterruptController(), 0.0
    )
    assert result == "hi:yo"
    assert calls == {"place": 1, "execute": 1}


@pytest.mark.asyncio
async def test_wedged_worker_torn_down_not_process_exit():
    """A ``WorkerWedgedError`` tears down only that session's worker and returns
    a terminal message — no whole-process exit."""

    torn = []

    class _WedgingExecutor:
        async def place(self, session_id):
            return TurnPlacement(session_id=session_id, worker_id="w", epoch=0)

        async def execute_turn(self, placement, turn, *, cancel_token=None, limits=None):
            raise WorkerWedgedError("wedged")

        async def teardown(self, placement, *, reason):
            torn.append((placement.session_id, reason))

    gw = WebSocketGateway(config=GatewayConfig(executor=_WedgingExecutor()))
    from praisonaiagents.agent.interrupt import InterruptController

    result = await gw._drive_turn(
        _session("s9"), _Agent(), "hello", InterruptController(), 0.0
    )
    assert "wedged" in result.lower()
    assert torn == [("s9", "wedged")]
    # The turn must be cleared from the active registry after a wedge.
    assert "s9" not in gw._active_turns
    # A wedge is a failure, not a successful reply: the terminal turn must carry
    # a non-ok outcome so the session queue does not persist/deliver it as ok.
    assert getattr(result, "outcome_status", "ok") == "error"


@pytest.mark.asyncio
async def test_normal_turn_carries_no_failure_outcome():
    """A successful reply must not be tagged as a failure outcome."""

    gw = WebSocketGateway()
    from praisonaiagents.agent.interrupt import InterruptController

    result = await gw._drive_turn(
        _session(), _Agent("r"), "m", InterruptController(), 0.0
    )
    assert result == "r:m"
    # Plain replies carry no explicit outcome; the queue defaults them to ok.
    assert getattr(result, "outcome_status", "ok") == "ok"


@pytest.mark.asyncio
async def test_default_inprocess_still_runs_turn_on_loop():
    """Backward compatibility: with no executor configured the turn still runs
    and returns its result exactly as before."""

    gw = WebSocketGateway()
    from praisonaiagents.agent.interrupt import InterruptController

    result = await gw._drive_turn(
        _session(), _Agent("r"), "m", InterruptController(), 0.0
    )
    assert result == "r:m"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
