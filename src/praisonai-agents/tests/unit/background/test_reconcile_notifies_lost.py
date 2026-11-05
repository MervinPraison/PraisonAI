"""Restart reconciliation announces LOST jobs (Issue #6038)."""

from praisonaiagents.background.job_manager import (
    BackgroundJobManager, JobInfo, JobStatus,
)
from praisonaiagents.background.sqlite_store import SqliteBackgroundJobStore
from praisonaiagents.hooks import add_hook
from praisonaiagents.hooks.registry import remove_hook


def _store(tmp_path):
    return SqliteBackgroundJobStore(str(tmp_path / "jobs.db"))


def _orphan(store, origin):
    store.upsert(JobInfo(job_id="job-42", status=JobStatus.RUNNING,
                         started_at=1.0, origin=origin))


ORIGIN = {"deliver": "telegram:12345", "task": "audit all 40 repos"}


def test_lost_job_fires_hook_once_and_is_redelivered(tmp_path):
    store = _store(tmp_path)
    _orphan(store, ORIGIN)
    heard = []
    hook_id = add_hook("job_completed", lambda inp: heard.append(inp) or None)
    try:
        _check_lost_flow(store, heard)
    finally:
        remove_hook(hook_id)


def _check_lost_flow(store, heard):

    # First pass (get_job_manager's lazy one): no redeliver.
    BackgroundJobManager(store=store).reconcile_on_start()
    info = store.get("job-42")
    assert info.status == JobStatus.LOST
    assert info.error and "restart" in info.error
    assert not info.delivered
    assert len(heard) == 1
    assert heard[0].job_id == "job-42"
    assert heard[0].status == "lost"

    # Boot pass with redeliver: exactly one notice, then delivered.
    sent = []
    counts = BackgroundJobManager(store=store).reconcile_on_start(redeliver=sent.append)
    assert [j.status for j in sent] == [JobStatus.LOST]
    assert counts["redelivered"] == 1
    assert store.get("job-42").delivered
    assert len(heard) == 1  # hook not re-fired

    sent.clear()
    BackgroundJobManager(store=store).reconcile_on_start(redeliver=sent.append)
    assert sent == []


def test_failed_redeliver_retries_next_boot(tmp_path):
    store = _store(tmp_path)
    _orphan(store, ORIGIN)

    def boom(job):
        raise RuntimeError("transport down")

    BackgroundJobManager(store=store).reconcile_on_start(redeliver=boom)
    assert not store.get("job-42").delivered
    sent = []
    BackgroundJobManager(store=store).reconcile_on_start(redeliver=sent.append)
    assert len(sent) == 1


def test_lost_job_without_origin_is_not_redelivered(tmp_path):
    store = _store(tmp_path)
    _orphan(store, {})
    sent = []
    BackgroundJobManager(store=store).reconcile_on_start(redeliver=sent.append)
    assert sent == []
    assert store.list_unreconciled() == []


def test_repeat_call_skips_jobs_live_in_this_process(tmp_path):
    import threading

    store = _store(tmp_path)
    mgr = BackgroundJobManager(store=store)
    gate = threading.Event()
    job_id = mgr.start_job(lambda: gate.wait(5))
    try:
        mgr.reconcile_on_start(redeliver=lambda j: None)
        assert mgr.get_job_info(job_id).status in (JobStatus.PENDING, JobStatus.RUNNING)
    finally:
        gate.set()
        mgr.shutdown()


def test_job_completing_during_scan_is_not_marked_lost(tmp_path):
    store = _store(tmp_path)
    mgr = BackgroundJobManager(store=store)
    job_id = mgr.start_job(lambda: "done", origin=ORIGIN)
    mgr.get_result(job_id, timeout=5)
    # Stale RUNNING snapshot, as if listed before the worker finished.
    stale = JobInfo(job_id=job_id, status=JobStatus.RUNNING, origin=ORIGIN)
    mgr._store = type("S", (), {
        "list_unreconciled": lambda self: [stale],
        "upsert": store.upsert, "get": store.get,
    })()
    sent = []
    counts = mgr.reconcile_on_start(redeliver=sent.append)
    assert counts["lost"] == 0 and sent == []
    assert mgr.get_job_info(job_id).status == JobStatus.COMPLETED
    assert store.get(job_id).status == JobStatus.COMPLETED
    mgr.shutdown()
