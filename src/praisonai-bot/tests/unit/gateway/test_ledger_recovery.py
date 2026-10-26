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

    async def _fake_notice(channel_target, text, run_id):
        sent.append((channel_target, text, run_id))
        return True

    gateway._deliver_lost_run_notice = _fake_notice

    recovered = asyncio.run(gateway._recover_orphaned_runs())

    assert recovered == 1
    assert len(sent) == 1
    assert sent[0][0] == "telegram:42"
    assert sent[0][2] == "r1"
    assert ledger.closed is True


def test_lost_run_notice_uses_durable_outbox(monkeypatch):
    """The notice is persisted to the durable outbox *before* delivery.

    Issue #3881 (review): ``recover_orphans`` terminalises a run to ``LOST`` and
    never re-scans it, so the notice must survive a not-ready transport. Verify
    the durable ``scheduled_outbox`` path is taken with a stable
    ``run-recovery:{run_id}`` key rather than the in-process-only router path.
    """
    gateway = _make_gateway()

    enqueued = {}

    class _FakeRouter:
        pass

    class _FakeOutbox:
        pass

    monkeypatch.setattr(
        type(gateway), "delivery_router",
        property(lambda self: _FakeRouter()),
    )
    monkeypatch.setattr(
        type(gateway), "scheduled_outbox",
        property(lambda self: _FakeOutbox()),
    )

    async def _fake_via_outbox(outbox, router, route, text, idem):
        enqueued["route"] = route
        enqueued["idem"] = idem
        return True

    gateway._deliver_via_outbox = _fake_via_outbox

    ok = asyncio.run(
        gateway._deliver_lost_run_notice("telegram:42", "hi", "r1")
    )

    assert ok is True
    assert enqueued["route"] == "telegram:42"
    assert enqueued["idem"] == "run-recovery:r1"


def test_lost_run_notice_falls_back_without_outbox(monkeypatch):
    """No durable outbox => best-effort restart-notice path is used."""
    gateway = _make_gateway()
    monkeypatch.setattr(
        type(gateway), "delivery_router", property(lambda self: None),
    )
    monkeypatch.setattr(
        type(gateway), "scheduled_outbox", property(lambda self: None),
    )

    called = {}

    async def _fake_restart(channel_target, text, session_id, run_epoch):
        called["channel_target"] = channel_target
        called["session_id"] = session_id
        return True

    gateway._deliver_restart_notice = _fake_restart

    ok = asyncio.run(
        gateway._deliver_lost_run_notice("telegram:42", "hi", "r1")
    )

    assert ok is True
    assert called["channel_target"] == "telegram:42"
    assert called["session_id"] == "run:r1"


def test_recover_orphaned_runs_marks_delivered_on_success(monkeypatch):
    """A successful wake-back marks the ledger delivered (exactly-once).

    Issue #4830: recover_orphans now re-surfaces every *undelivered* LOST run
    so a failed notice retries on the next boot. The gateway must therefore
    mark a run delivered once its notice lands, or a delivered run would be
    re-notified on every subsequent boot.
    """
    from praisonaiagents.runs import RunRecord, RunStatus

    lost = [
        RunRecord(run_id="ok", channel="telegram", thread_id="1",
                  status=RunStatus.LOST),
        RunRecord(run_id="fail", channel="telegram", thread_id="2",
                  status=RunStatus.LOST),
    ]

    class _FakeLedger:
        def __init__(self):
            self.marked = []

        def recover_orphans(self):
            return lost

        def mark_delivered(self, run_id):
            self.marked.append(run_id)

        def close(self):
            pass

    ledger = _FakeLedger()
    gateway = _make_gateway()
    monkeypatch.setattr(gateway, "_open_run_ledger", lambda: ledger)

    async def _fake_notice(channel_target, text, run_id):
        # "ok" delivers; "fail" does not (left undelivered for retry).
        return run_id == "ok"

    gateway._deliver_lost_run_notice = _fake_notice

    recovered = asyncio.run(gateway._recover_orphaned_runs())

    assert recovered == 1
    # Only the delivered run is marked; the failed one stays undelivered so a
    # later boot's recover_orphans returns it again.
    assert ledger.marked == ["ok"]


def test_recover_orphaned_runs_marks_delivered_when_no_route(monkeypatch):
    """A run with no origin route is marked delivered to stop re-surfacing."""
    from praisonaiagents.runs import RunRecord, RunStatus

    lost = [RunRecord(run_id="orphan", channel="", status=RunStatus.LOST)]

    class _FakeLedger:
        def __init__(self):
            self.marked = []

        def recover_orphans(self):
            return lost

        def mark_delivered(self, run_id):
            self.marked.append(run_id)

        def close(self):
            pass

    ledger = _FakeLedger()
    gateway = _make_gateway()
    monkeypatch.setattr(gateway, "_open_run_ledger", lambda: ledger)

    recovered = asyncio.run(gateway._recover_orphaned_runs())

    assert recovered == 0
    assert ledger.marked == ["orphan"]


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


def test_reconcile_background_jobs_notifies_lost_job_once(tmp_path, monkeypatch):
    """Issue #6038: a job RUNNING at restart gets one 'interrupted' notice."""
    import praisonaiagents.background.job_manager as jm
    from praisonaiagents.background.job_manager import JobInfo, JobStatus
    from praisonaiagents.background.sqlite_store import SqliteBackgroundJobStore

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    pre = SqliteBackgroundJobStore()
    pre.upsert(JobInfo(
        job_id="job-42", status=JobStatus.RUNNING, started_at=1.0,
        origin={"deliver": "origin", "platform": "telegram",
                "chat_id": "12345", "task": "audit all 40 repos"},
    ))
    pre.close()
    monkeypatch.setattr(jm, "_global_job_manager", None)

    gateway = _make_gateway()
    sent = []

    async def _notice(target, text, run_id):
        sent.append((target, text, run_id))
        return True

    monkeypatch.setattr(gateway, "_deliver_lost_run_notice", _notice)
    try:
        assert asyncio.run(gateway._reconcile_background_jobs()) == 1
        assert asyncio.run(gateway._reconcile_background_jobs()) == 0
    finally:
        mgr, jm._global_job_manager = jm._global_job_manager, None
        if mgr is not None:
            mgr.shutdown(wait=False)
    assert len(sent) == 1
    target, text, run_id = sent[0]
    assert target == "telegram:12345"
    assert "audit all 40 repos" in text and "interrupted" in text
    assert run_id == "job:job-42:telegram:12345"


def test_resolve_job_routes_keeps_thread_and_resolves_targets():
    """Recovery uses the live delivery rules: thread kept, aliases resolved."""
    gateway = _make_gateway()
    origin = {"platform": "slack", "chat_id": "C1", "thread_id": "T9"}
    assert gateway._resolve_job_routes({**origin, "deliver": "origin"}) == ["slack:C1:T9"]
    assert gateway._resolve_job_routes({"deliver": ""}) == []
    assert gateway._resolve_job_routes({"deliver": "origin"}) == []

    class _Router:
        def resolve(self, target):
            if target == "ops":
                return ("slack", "C2", None)
            raise ValueError(target)

    gateway._delivery_router = _Router()
    try:
        assert gateway._resolve_job_routes({**origin, "deliver": "ops"}) == ["slack:C2"]
        # Not resolvable now: raise so the job is retried, not marked delivered.
        with pytest.raises(ValueError):
            gateway._resolve_job_routes({**origin, "deliver": "nowhere"})
        with pytest.raises(RuntimeError):
            gateway._resolve_job_routes({**origin, "deliver": "all"})
    finally:
        gateway._delivery_router = None


def test_reconcile_background_jobs_retries_until_every_route_succeeds(tmp_path, monkeypatch):
    """A partial fan-out failure leaves the job undelivered for the next boot."""
    import praisonaiagents.background.job_manager as jm
    from praisonaiagents.background.job_manager import JobInfo, JobStatus
    from praisonaiagents.background.sqlite_store import SqliteBackgroundJobStore

    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    pre = SqliteBackgroundJobStore()
    pre.upsert(JobInfo(
        job_id="job-7", status=JobStatus.RUNNING, started_at=1.0,
        origin={"deliver": "all", "task": "nightly report"},
    ))
    pre.close()
    monkeypatch.setattr(jm, "_global_job_manager", None)

    gateway = _make_gateway()
    monkeypatch.setattr(
        gateway, "_resolve_job_routes",
        lambda origin: ["slack:C1", "telegram:42"],
    )
    down = {"telegram:42"}
    sent = []

    async def _notice(target, text, run_id):
        if target in down:
            return False
        sent.append(target)
        return True

    monkeypatch.setattr(gateway, "_deliver_lost_run_notice", _notice)
    try:
        assert asyncio.run(gateway._reconcile_background_jobs()) == 0
        assert not jm._global_job_manager.get_job_info("job-7").delivered
        down.clear()
        assert asyncio.run(gateway._reconcile_background_jobs()) == 1
    finally:
        mgr, jm._global_job_manager = jm._global_job_manager, None
        if mgr is not None:
            mgr.shutdown(wait=False)
    assert "telegram:42" in sent
