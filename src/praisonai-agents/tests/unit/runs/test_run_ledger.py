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
)


# ── protocol / data shapes ────────────────────────────────────────────


def test_run_status_terminal_and_active_partition():
    all_statuses = set(RunStatus)
    assert ACTIVE_STATUSES | TERMINAL_STATUSES == all_statuses
    assert not (ACTIVE_STATUSES & TERMINAL_STATUSES)
    assert RunStatus.RUNNING.is_active
    assert not RunStatus.RUNNING.is_terminal
    assert RunStatus.SUCCEEDED.is_terminal
    assert RunStatus.LOST.is_terminal


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


def test_from_dict_unknown_status_becomes_lost():
    rec = RunRecord.from_dict({"run_id": "r1", "status": "bogus"})
    assert rec.status == RunStatus.LOST


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
    # Idempotent: nothing active left to recover.
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
