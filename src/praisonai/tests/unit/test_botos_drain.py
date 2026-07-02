"""Unit tests for BotOS graceful drain on shutdown (Issue #2375).

Verifies that ``BotOS.drain`` quiesces ingress, waits (bounded) for
in-flight agent turns to finish, and reports abandoned turns on timeout,
while remaining a no-op when no drain timeout is configured.
"""

import asyncio

import pytest

try:
    from praisonai.bots.botos import BotOS
except ImportError:  # pragma: no cover - optional deps not installed
    BotOS = None

pytestmark = pytest.mark.skipif(BotOS is None, reason="praisonai bots not importable")


class _FakeSession:
    def __init__(self, active_runs=None):
        self._active_runs = active_runs or {}
        self._last_active = {}


class _FakeBot:
    def __init__(self, session):
        self.platform = "fake"
        self._session = session


def test_drain_disabled_by_default_is_noop():
    """reliability='off' preserves immediate-teardown (no drain window)."""
    botos = BotOS(reliability="off")
    abandoned = asyncio.run(botos.drain())
    assert abandoned == 0
    assert botos.accepting is True
    assert botos.is_draining is False


def test_drain_default_reliability_quiesces_ingress():
    """Default reliability applies a small drain window (#2531)."""
    botos = BotOS()
    assert botos._drain_timeout == 5.0
    abandoned = asyncio.run(botos.drain())
    assert abandoned == 0
    assert botos.accepting is False
    assert botos.is_draining is True


def test_drain_zero_timeout_is_noop():
    botos = BotOS(drain_timeout=0)
    abandoned = asyncio.run(botos.drain())
    assert abandoned == 0


def test_drain_completes_when_no_turns():
    botos = BotOS(drain_timeout=5)
    botos._bots = {"fake": _FakeBot(_FakeSession(active_runs={}))}
    abandoned = asyncio.run(botos.drain(timeout=2))
    assert abandoned == 0
    # Ingress is quiesced during drain.
    assert botos.accepting is False
    assert botos.is_draining is True


def test_drain_times_out_with_in_flight_turns():
    botos = BotOS(drain_timeout=1)
    # Two never-completing turns: drain must time out and report them.
    botos._bots = {
        "fake": _FakeBot(_FakeSession(active_runs={"u1": object(), "u2": object()}))
    }
    abandoned = asyncio.run(botos.drain(timeout=1))
    assert abandoned == 2


def test_drain_waits_then_completes_when_turn_finishes():
    botos = BotOS(drain_timeout=5)
    session = _FakeSession(active_runs={"u1": object()})
    botos._bots = {"fake": _FakeBot(session)}

    async def _run():
        async def _finish_soon():
            await asyncio.sleep(0.6)
            session._active_runs.clear()  # turn completes mid-drain

        finisher = asyncio.create_task(_finish_soon())
        abandoned = await botos.drain(timeout=5)
        await finisher
        return abandoned

    abandoned = asyncio.run(_run())
    assert abandoned == 0


def test_drain_timeout_from_constructor_used_by_default():
    botos = BotOS(drain_timeout=1)
    botos._bots = {"fake": _FakeBot(_FakeSession(active_runs={"u1": object()}))}
    abandoned = asyncio.run(botos.drain())  # no explicit timeout -> use ctor value
    assert abandoned == 1
