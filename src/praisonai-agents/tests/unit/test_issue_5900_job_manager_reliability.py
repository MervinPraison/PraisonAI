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
    try:
        m.start_job(gate.wait, job_id="x")
        _wait_status(m, "x", JobStatus.RUNNING)
        with pytest.raises(ValueError):
            m.start_job(lambda: "B", job_id="x")
        gate.set()
        m.get_result("x", timeout=5)
        m.start_job(lambda: "B", job_id="x")
        assert m.get_result("x", timeout=5) == "B"
    finally:
        gate.set()
        m.shutdown()


def test_auto_job_id_is_longer():
    m = BackgroundJobManager(max_workers=1)
    try:
        assert len(m.start_job(lambda: 1)) >= 12
    finally:
        m.shutdown()


def test_running_job_can_be_cancelled_and_result_discarded():
    m = BackgroundJobManager(max_workers=1)
    gate = threading.Event()
    delivered = []
    try:
        m.start_job(lambda: gate.wait() and "late", job_id="r", on_complete=delivered.append)
        _wait_status(m, "r", JobStatus.RUNNING)
        assert m.cancel_job("r") is True
        assert m.get_status("r") == JobStatus.CANCELLED
        with pytest.raises(CancelledError):
            m.get_result("r", timeout=0.1)
    finally:
        gate.set()
        m.shutdown(wait=True)
    assert m.get_status("r") == JobStatus.CANCELLED
    assert m.get_job_info("r").result is None
    assert delivered == []


def test_cancel_wakes_untimed_result_waiter():
    m = BackgroundJobManager(max_workers=1)
    gate = threading.Event()
    outcome = []

    def waiter():
        try:
            m.get_result("w")
        except CancelledError:
            outcome.append("cancelled")

    try:
        m.start_job(gate.wait, job_id="w")
        _wait_status(m, "w", JobStatus.RUNNING)
        t = threading.Thread(target=waiter, daemon=True)
        t.start()
        time.sleep(0.05)
        assert m.cancel_job("w") is True
        t.join(timeout=2)
        assert outcome == ["cancelled"]
    finally:
        gate.set()
        m.shutdown()


def test_cancel_pending_job_never_runs():
    m = BackgroundJobManager(max_workers=1)
    gate = threading.Event()
    ran = []
    try:
        m.start_job(gate.wait, job_id="blocker")
        m.start_job(lambda: ran.append(1), job_id="p")
        assert m.cancel_job("p") is True
        with pytest.raises(CancelledError):
            m.get_result("p")
    finally:
        gate.set()
        m.shutdown(wait=True)
    assert ran == []
    assert m.cancel_job("p") is False


def test_stale_callback_does_not_overwrite_reused_id_in_store():
    store = SqliteBackgroundJobStore(":memory:")
    m = BackgroundJobManager(max_workers=2, store=store)
    in_callback = threading.Event()
    release = threading.Event()
    gate = threading.Event()

    def slow_callback(info):
        in_callback.set()
        release.wait(5)

    try:
        m.start_job(lambda: "old", job_id="id", on_complete=slow_callback, origin={"chat_id": "1"})
        assert in_callback.wait(5)
        m.start_job(gate.wait, job_id="id")
        _wait_status(m, "id", JobStatus.RUNNING)
        release.set()
        time.sleep(0.1)
        persisted = store.get("id")
        assert persisted.status == JobStatus.RUNNING
        assert persisted.result is None
    finally:
        release.set()
        gate.set()
        m.shutdown()


def test_get_result_timeout_raises_builtin_timeout_error():
    m = BackgroundJobManager(max_workers=1)
    gate = threading.Event()
    try:
        m.start_job(gate.wait, job_id="t")
        with pytest.raises(TimeoutError, match="did not complete"):
            m.get_result("t", timeout=0.05)
    finally:
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
    try:
        m.cleanup_completed(max_age=3600)
        assert store.get("old") is None
        assert store.get("undelivered") is not None
        assert store.get("fresh") is not None
        assert store.get("running") is not None
    finally:
        m.shutdown()


def test_submit_after_shutdown_fails_job_and_frees_id():
    m = BackgroundJobManager(max_workers=1)
    m.shutdown()
    seen = []
    with pytest.raises(RuntimeError):
        m.start_job(lambda: "A", job_id="x", on_complete=seen.append)
    assert m.get_status("x") == JobStatus.FAILED
    assert [i.status for i in seen] == [JobStatus.FAILED]  # failure not silent
    with pytest.raises(RuntimeError):
        m.get_result("x")  # resolved, not blocking forever


def test_callback_base_exception_still_resolves_result():
    class Stop(BaseException):
        pass

    def boom(_info):
        raise Stop()

    m = BackgroundJobManager(max_workers=1)
    try:
        m.start_job(lambda: "A", job_id="x", on_complete=boom)
        assert m.get_result("x", timeout=5) == "A"
    finally:
        m.shutdown()


def test_func_base_exception_fails_job_and_resolves_result():
    m = BackgroundJobManager(max_workers=1)
    delivered = threading.Event()
    seen = []

    def on_complete(info):
        seen.append(info.status)
        delivered.set()

    try:
        m.start_job(
            lambda: (_ for _ in ()).throw(SystemExit()), job_id="x",
            on_complete=on_complete,
        )
        with pytest.raises(SystemExit):
            m.get_result("x", timeout=5)
        assert m.get_status("x") == JobStatus.FAILED
        assert m.list_jobs()["x"].error == "SystemExit"  # never an empty error
        assert delivered.wait(5) and seen == [JobStatus.FAILED]  # failure not silent
    finally:
        m.shutdown()


def test_queued_job_dropped_at_shutdown_is_cancelled():
    m = BackgroundJobManager(max_workers=1)
    gate = threading.Event()
    try:
        m.start_job(gate.wait, job_id="a")
        _wait_status(m, "a", JobStatus.RUNNING)
        seen = []
        m.start_job(lambda: "B", job_id="b", on_complete=seen.append)
        m._executor.shutdown(wait=False, cancel_futures=True)
        assert m.get_status("b") == JobStatus.CANCELLED
        with pytest.raises(CancelledError):
            m.get_result("b")
        assert seen == []  # cancellations stay silent, like cancel_job()
    finally:
        gate.set()
        m.shutdown()
