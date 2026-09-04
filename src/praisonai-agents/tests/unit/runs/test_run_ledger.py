"""Tests for the durable, recoverable run ledger (Issue #2924)."""

import os
import tempfile

import pytest

from praisonaiagents.runs import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    RunLedgerProtocol,
    RunRecord,
    RunStatus,
    SQLiteRunLedger,
    TerminalOutcomeDelivererProtocol,
    notify_recovered,
)


# ── protocol / data shapes ────────────────────────────────────────────


def test_run_status_terminal_and_active_partition():
    # Every known status is either active or terminal, except the UNKNOWN
    # forward-compat sentinel which is deliberately neither.
    classified = ACTIVE_STATUSES | TERMINAL_STATUSES
    assert classified == set(RunStatus) - {RunStatus.UNKNOWN}
    assert not (ACTIVE_STATUSES & TERMINAL_STATUSES)
    assert RunStatus.RUNNING.is_active
    assert not RunStatus.RUNNING.is_terminal
    assert RunStatus.SUCCEEDED.is_terminal
    assert RunStatus.LOST.is_terminal
    # UNKNOWN is neither active nor terminal so recovery never finalises it.
    assert not RunStatus.UNKNOWN.is_active
    assert not RunStatus.UNKNOWN.is_terminal


def test_run_status_is_str_enum():
    assert RunStatus.RUNNING == "running"
    assert RunStatus.RUNNING.value == "running"


def test_run_record_roundtrip():
    rec = RunRecord(
        run_id="r1",
        agent_id="agent-x",
        channel="#ops",
        thread_id="t42",
        status=RunStatus.RUNNING,
        progress="step 2/5",
        metadata={"k": "v"},
    )
    restored = RunRecord.from_dict(rec.to_dict())
    assert restored.run_id == "r1"
    assert restored.agent_id == "agent-x"
    assert restored.channel == "#ops"
    assert restored.thread_id == "t42"
    assert restored.status == RunStatus.RUNNING
    assert restored.progress == "step 2/5"
    assert restored.metadata == {"k": "v"}


def test_from_dict_unknown_status_becomes_unknown():
    # A status a newer writer introduced must not be finalised as LOST here:
    # it maps to the non-terminal UNKNOWN sentinel so the run is not dropped.
    rec = RunRecord.from_dict({"run_id": "r1", "status": "bogus"})
    assert rec.status == RunStatus.UNKNOWN
    assert not rec.status.is_terminal
    assert not rec.status.is_active


def test_sqlite_ledger_satisfies_protocol():
    ledger = SQLiteRunLedger(db_path=":memory:")
    assert isinstance(ledger, RunLedgerProtocol)


# ── SQLite ledger ─────────────────────────────────────────────────────


@pytest.fixture
def ledger():
    lg = SQLiteRunLedger(db_path=":memory:")
    yield lg
    lg.close()


def test_upsert_and_get(ledger):
    ledger.upsert(RunRecord(run_id="r1", channel="#a", status=RunStatus.QUEUED))
    got = ledger.get("r1")
    assert got is not None
    assert got.run_id == "r1"
    assert got.channel == "#a"
    assert got.status == RunStatus.QUEUED


def test_get_unknown_returns_none(ledger):
    assert ledger.get("nope") is None


def test_upsert_updates_existing(ledger):
    ledger.upsert(RunRecord(run_id="r1", status=RunStatus.QUEUED))
    ledger.upsert(
        RunRecord(
            run_id="r1",
            status=RunStatus.SUCCEEDED,
            terminal_outcome="done",
        )
    )
    got = ledger.get("r1")
    assert got.status == RunStatus.SUCCEEDED
    assert got.terminal_outcome == "done"


def test_list_active_excludes_terminal(ledger):
    ledger.upsert(RunRecord(run_id="a", status=RunStatus.RUNNING))
    ledger.upsert(RunRecord(run_id="b", status=RunStatus.WAITING))
    ledger.upsert(RunRecord(run_id="c", status=RunStatus.SUCCEEDED))
    ledger.upsert(RunRecord(run_id="d", status=RunStatus.FAILED))
    active_ids = {r.run_id for r in ledger.list_active()}
    assert active_ids == {"a", "b"}


def test_recover_orphans_marks_active_as_lost(ledger):
    ledger.upsert(RunRecord(run_id="a", channel="#a", status=RunStatus.RUNNING))
    ledger.upsert(RunRecord(run_id="b", status=RunStatus.SUCCEEDED))
    recovered = ledger.recover_orphans()
    assert {r.run_id for r in recovered} == {"a"}
    assert ledger.get("a").status == RunStatus.LOST
    assert ledger.get("a").terminal_outcome
    # Terminal runs are untouched.
    assert ledger.get("b").status == RunStatus.SUCCEEDED
    # A LOST run stays owed a wake-back until it is delivered: recover_orphans
    # re-surfaces it (retry) rather than dropping it. Once delivered, it is
    # never returned again — the exactly-once boundary is mark_delivered.
    assert {r.run_id for r in ledger.recover_orphans()} == {"a"}
    ledger.mark_delivered("a")
    assert ledger.recover_orphans() == []


def test_recover_orphans_preserves_origin_route(ledger):
    ledger.upsert(
        RunRecord(
            run_id="a",
            channel="#ops",
            thread_id="t7",
            status=RunStatus.RUNNING,
        )
    )
    recovered = ledger.recover_orphans()
    assert recovered[0].channel == "#ops"
    assert recovered[0].thread_id == "t7"


def test_list_all_newest_first(ledger):
    ledger.upsert(RunRecord(run_id="a", status=RunStatus.QUEUED))
    ledger.upsert(RunRecord(run_id="b", status=RunStatus.QUEUED))
    ids = [r.run_id for r in ledger.list_all()]
    assert set(ids) == {"a", "b"}


def test_upsert_accepts_non_json_native_metadata(ledger):
    import datetime

    rec = RunRecord(
        run_id="r1",
        status=RunStatus.RUNNING,
        metadata={
            "when": datetime.datetime(2024, 1, 1, 12, 0, 0),
            "tags": {"a", "b"},
        },
    )
    # Must not raise: a run with rich metadata is still durably recorded.
    ledger.upsert(rec)
    got = ledger.get("r1")
    assert got is not None
    assert got.status == RunStatus.RUNNING


def test_recover_orphans_does_not_overwrite_completed_run(ledger):
    # A run that completed (terminal) before recovery runs must be preserved.
    ledger.upsert(RunRecord(run_id="done", status=RunStatus.SUCCEEDED,
                            terminal_outcome="ok"))
    ledger.upsert(RunRecord(run_id="live", status=RunStatus.RUNNING))
    recovered = ledger.recover_orphans()
    assert {r.run_id for r in recovered} == {"live"}
    assert ledger.get("done").status == RunStatus.SUCCEEDED
    assert ledger.get("done").terminal_outcome == "ok"
    assert ledger.get("live").status == RunStatus.LOST


def test_recover_orphans_preserves_existing_terminal_outcome(ledger):
    ledger.upsert(RunRecord(run_id="a", status=RunStatus.RUNNING,
                            terminal_outcome="partial note"))
    ledger.recover_orphans()
    assert ledger.get("a").status == RunStatus.LOST
    assert ledger.get("a").terminal_outcome == "partial note"


def test_durability_across_reopen():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.db")
        lg1 = SQLiteRunLedger(db_path=path)
        lg1.upsert(
            RunRecord(run_id="r1", channel="#c", status=RunStatus.RUNNING)
        )
        lg1.close()

        # Simulate a gateway restart: reopen the same file.
        lg2 = SQLiteRunLedger(db_path=path)
        got = lg2.get("r1")
        assert got is not None
        assert got.status == RunStatus.RUNNING
        recovered = lg2.recover_orphans()
        assert {r.run_id for r in recovered} == {"r1"}
        assert lg2.get("r1").status == RunStatus.LOST
        lg2.close()


# ── exactly-once terminal-outcome wake-back (Issue #4830) ─────────────


class _RecordingDeliverer:
    """Test transport recording every record it is asked to deliver."""

    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.delivered: list = []

    async def deliver_terminal(self, record: RunRecord) -> bool:
        self.delivered.append(record)
        return self.succeed


def test_terminal_outcome_deliverer_protocol_runtime_checkable():
    assert isinstance(_RecordingDeliverer(), TerminalOutcomeDelivererProtocol)


def test_run_record_delivered_roundtrips():
    rec = RunRecord(run_id="r1", status=RunStatus.LOST, delivered=True)
    assert RunRecord.from_dict(rec.to_dict()).delivered is True
    # Defaults to False for records/dicts that predate the field.
    assert RunRecord.from_dict({"run_id": "r2"}).delivered is False


@pytest.mark.asyncio
async def test_notify_recovered_delivers_each_lost_run_once(ledger):
    ledger.upsert(
        RunRecord(run_id="a", channel="#ops", thread_id="t1",
                  status=RunStatus.RUNNING)
    )
    ledger.upsert(RunRecord(run_id="b", channel="#ops",
                            status=RunStatus.RUNNING))
    deliverer = _RecordingDeliverer(succeed=True)

    count = await notify_recovered(ledger, deliverer)

    assert count == 2
    assert {r.run_id for r in deliverer.delivered} == {"a", "b"}
    # Each recovered run is now LOST and marked delivered.
    assert ledger.get("a").status == RunStatus.LOST
    assert ledger.get("a").delivered is True
    assert ledger.get("b").delivered is True

    # A second recovery pass has nothing undelivered to wake — exactly once.
    deliverer2 = _RecordingDeliverer(succeed=True)
    assert await notify_recovered(ledger, deliverer2) == 0
    assert deliverer2.delivered == []


@pytest.mark.asyncio
async def test_notify_recovered_failed_delivery_is_retryable(ledger):
    ledger.upsert(RunRecord(run_id="a", channel="#ops",
                            status=RunStatus.RUNNING))
    failing = _RecordingDeliverer(succeed=False)

    assert await notify_recovered(ledger, failing) == 0
    # LOST is recorded, but the run is NOT marked delivered — a visible,
    # retryable non-outcome rather than a silent one.
    assert ledger.get("a").status == RunStatus.LOST
    assert ledger.get("a").delivered is False

    # Retry is automatic on the next recovery pass: recover_orphans returns
    # every undelivered LOST run (not only freshly-reconciled ones), so a
    # later working transport delivers it without any manual re-arming.
    working = _RecordingDeliverer(succeed=True)
    assert await notify_recovered(ledger, working) == 1
    assert {r.run_id for r in working.delivered} == {"a"}
    assert ledger.get("a").delivered is True

    # And now that it is delivered, it is never surfaced again (exactly-once).
    assert await notify_recovered(ledger, _RecordingDeliverer(succeed=True)) == 0


@pytest.mark.asyncio
async def test_notify_recovered_transport_exception_is_treated_as_miss(ledger):
    ledger.upsert(RunRecord(run_id="a", channel="#ops",
                            status=RunStatus.RUNNING))

    class _Boom:
        async def deliver_terminal(self, record):
            raise RuntimeError("channel down")

    # A raising transport must not crash recovery; the run stays undelivered.
    assert await notify_recovered(ledger, _Boom()) == 0
    assert ledger.get("a").status == RunStatus.LOST
    assert ledger.get("a").delivered is False


def test_mark_delivered_persists_across_reopen():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.db")
        lg1 = SQLiteRunLedger(db_path=path)
        lg1.upsert(RunRecord(run_id="r1", status=RunStatus.LOST))
        lg1.mark_delivered("r1")
        assert lg1.get("r1").delivered is True
        lg1.close()

        lg2 = SQLiteRunLedger(db_path=path)
        assert lg2.get("r1").delivered is True
        lg2.close()


def test_migration_adds_delivered_column_to_old_ledger():
    # An older ledger.db has no ``delivered`` column. Opening it must apply the
    # additive migration so reads/upserts/recovery keep working.
    import sqlite3

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.db")
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL DEFAULT '',
                channel TEXT NOT NULL DEFAULT '',
                thread_id TEXT,
                status TEXT NOT NULL DEFAULT 'queued',
                progress TEXT,
                terminal_outcome TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                metadata TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO runs (run_id, status, created_at, updated_at) "
            "VALUES ('old', 'running', 1.0, 1.0)",
        )
        conn.commit()
        conn.close()

        lg = SQLiteRunLedger(db_path=path)
        got = lg.get("old")
        assert got is not None
        assert got.delivered is False  # migrated column defaults to 0
        # Recovery still works on the migrated ledger.
        recovered = lg.recover_orphans()
        assert {r.run_id for r in recovered} == {"old"}
        lg.close()


def test_recover_orphans_retries_undelivered_lost_across_reopen():
    # A LOST run left undelivered by a prior boot is re-surfaced by a later
    # recover_orphans (retry), while a delivered one is not (exactly-once).
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "ledger.db")
        lg1 = SQLiteRunLedger(db_path=path)
        lg1.upsert(RunRecord(run_id="undelivered", status=RunStatus.RUNNING))
        lg1.upsert(RunRecord(run_id="delivered", status=RunStatus.RUNNING))
        first = lg1.recover_orphans()
        assert {r.run_id for r in first} == {"undelivered", "delivered"}
        lg1.mark_delivered("delivered")
        lg1.close()

        # Restart: the undelivered LOST run is owed a retry; the delivered one
        # must never be woken again.
        lg2 = SQLiteRunLedger(db_path=path)
        again = lg2.recover_orphans()
        assert {r.run_id for r in again} == {"undelivered"}
        lg2.close()
