"""Regression tests for issue #5900 (BackgroundJobManager reliability)."""

import threading
import time
from concurrent.futures import CancelledError

import pytest

from praisonaiagents.background.job_manager import BackgroundJobManager, JobInfo, JobStatus
from praisonaiagents.background.sqlite_store import SqliteBackgroundJobStore


def _wait_status(m, job_id, status, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if m.get_status(job_id) == status:
            return
        time.sleep(0.01)
    raise AssertionError(f"{job_id} never reached {status}")


def test_reusing_active_job_id_raises_and_terminal_id_reusable():
    m = BackgroundJobManager(max_workers=1)
    gate = threading.Event()
    m.start_job(gate.wait, job_id="x")
    _wait_status(m, "x", JobStatus.RUNNING)
    with pytest.raises(ValueError):
        m.start_job(lambda: "B", job_id="x")
    gate.set()
    m.get_result("x", timeout=5)
    m.start_job(lambda: "B", job_id="x")
    assert m.get_result("x", timeout=5) == "B"
    m.shutdown()


def test_auto_job_id_is_longer():
    m = BackgroundJobManager(max_workers=1)
    assert len(m.start_job(lambda: 1)) >= 12
    m.shutdown()


def test_running_job_can_be_cancelled_and_result_discarded():
    m = BackgroundJobManager(max_workers=1)
    gate = threading.Event()
    delivered = []
    m.start_job(lambda: gate.wait() and "late", job_id="r", on_complete=delivered.append)
    _wait_status(m, "r", JobStatus.RUNNING)
    assert m.cancel_job("r") is True
    assert m.get_status("r") == JobStatus.CANCELLED
    with pytest.raises(CancelledError):
        m.get_result("r", timeout=0.1)
    gate.set()
    m.shutdown(wait=True)
    assert m.get_status("r") == JobStatus.CANCELLED
    assert m.get_job_info("r").result is None
    assert delivered == []


def test_get_result_timeout_raises_builtin_timeout_error():
    m = BackgroundJobManager(max_workers=1)
    gate = threading.Event()
    m.start_job(gate.wait, job_id="t")
    with pytest.raises(TimeoutError, match="did not complete"):
        m.get_result("t", timeout=0.05)
    gate.set()
    m.shutdown()


def test_cleanup_prunes_durable_store():
    store = SqliteBackgroundJobStore(":memory:")
    old = time.time() - 7200
    store.upsert(JobInfo(job_id="old", status=JobStatus.COMPLETED, completed_at=old))
    store.upsert(JobInfo(
        job_id="undelivered", status=JobStatus.COMPLETED, completed_at=old,
        origin={"chat_id": "1"},
    ))
    store.upsert(JobInfo(job_id="fresh", status=JobStatus.FAILED, completed_at=time.time()))
    store.upsert(JobInfo(job_id="running", status=JobStatus.RUNNING))
    m = BackgroundJobManager(max_workers=1, store=store)
    m.cleanup_completed(max_age=3600)
    assert store.get("old") is None
    assert store.get("undelivered") is not None
    assert store.get("fresh") is not None
    assert store.get("running") is not None
    m.shutdown()
