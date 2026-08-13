#!/usr/bin/env python3
"""Tests for durable run-ledger boot recovery in the gateway (Issue #3881).

Verifies the gateway drives the core ``SQLiteRunLedger.recover_orphans`` on
boot, reconciling runs a crashed process left in flight to ``LOST`` and waking
their origin channel/thread — instead of losing in-flight work silently.
"""

import asyncio

import pytest

from praisonai_bot.gateway.server import WebSocketGateway


def _make_gateway():
    return WebSocketGateway(port=0)


def test_channel_target_for_run_prefers_channel_and_thread():
    """``channel`` + ``thread_id`` => ``channel:thread`` origin."""
    gateway = _make_gateway()

    class _Rec:
        channel = "telegram"
        thread_id = "999"

    assert gateway._channel_target_for_run(_Rec()) == "telegram:999"


def test_channel_target_for_run_falls_back_to_encoded_channel():
    """A ``channel`` that itself encodes ``channel:target`` is used as-is."""
    gateway = _make_gateway()

    class _Rec:
        channel = "slack:C123"
        thread_id = None

    assert gateway._channel_target_for_run(_Rec()) == "slack:C123"


def test_channel_target_for_run_none_without_origin():
    """A run with no channel origin is not notified."""
    gateway = _make_gateway()

    class _Rec:
        channel = ""
        thread_id = None

    assert gateway._channel_target_for_run(_Rec()) is None


def test_recover_orphaned_runs_noop_without_ledger(monkeypatch):
    """No ledger DB => no-op, no crash, no notice."""
    gateway = _make_gateway()
    monkeypatch.setattr(gateway, "_open_run_ledger", lambda: None)
    recovered = asyncio.run(gateway._recover_orphaned_runs())
    assert recovered == 0


def test_recover_orphaned_runs_notifies_origin(monkeypatch):
    """A LOST run wakes its origin channel exactly once via the durable path."""
    from praisonaiagents.runs import RunRecord, RunStatus

    lost = [
        RunRecord(
            run_id="r1",
            channel="telegram",
            thread_id="42",
            status=RunStatus.LOST,
            terminal_outcome="lost: gateway restarted mid-run",
        ),
        RunRecord(
            run_id="r2",
            channel="",  # no origin -> skipped
            status=RunStatus.LOST,
        ),
    ]

    class _FakeLedger:
        def __init__(self):
            self.closed = False

        def recover_orphans(self):
            return lost

        def close(self):
            self.closed = True

    ledger = _FakeLedger()
    gateway = _make_gateway()
    monkeypatch.setattr(gateway, "_open_run_ledger", lambda: ledger)

    sent = []

    async def _fake_notice(channel_target, text, session_id, run_epoch):
        sent.append((channel_target, text, session_id, run_epoch))
        return True

    gateway._deliver_restart_notice = _fake_notice

    recovered = asyncio.run(gateway._recover_orphaned_runs())

    assert recovered == 1
    assert len(sent) == 1
    assert sent[0][0] == "telegram:42"
    assert sent[0][2] == "run:r1"
    assert ledger.closed is True


def test_recover_orphaned_runs_survives_recover_error(monkeypatch):
    """A ledger whose recover_orphans raises degrades to a no-op, not a crash."""
    class _BrokenLedger:
        def recover_orphans(self):
            raise RuntimeError("boom")

        def close(self):
            pass

    gateway = _make_gateway()
    monkeypatch.setattr(gateway, "_open_run_ledger", lambda: _BrokenLedger())
    recovered = asyncio.run(gateway._recover_orphaned_runs())
    assert recovered == 0


def test_open_run_ledger_returns_none_when_db_missing(tmp_path, monkeypatch):
    """No ledger DB file yet => nothing to recover, no empty DB created."""
    import praisonaiagents.paths as paths

    monkeypatch.setattr(paths, "get_runs_dir", lambda: tmp_path)
    gateway = _make_gateway()
    assert gateway._open_run_ledger() is None
    assert not (tmp_path / "ledger.db").exists()
