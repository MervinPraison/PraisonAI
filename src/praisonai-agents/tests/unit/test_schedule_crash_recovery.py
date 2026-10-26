"""
Crash recovery for claimed schedule jobs (issue #6036).

A spent job (one-shot / ``max_runs`` met) is no longer deleted at claim time:
it stays leased and is retired on completion. A lease that expires without
``complete`` is recorded as an ``abandoned`` run; a one-shot is retried once,
a recurring job waits for its next slot. Covers both stores.
"""

import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore
from praisonaiagents.scheduler.models import Schedule, ScheduleJob
from praisonaiagents.scheduler.runner import ScheduleRunner
from praisonaiagents.scheduler.store import FileScheduleStore


@pytest.fixture(params=["file", "yaml"])
def make_store(request, tmp_path):
    if request.param == "file":
        return lambda: FileScheduleStore(store_dir=str(tmp_path))
    path = os.path.join(str(tmp_path), "config.yaml")
    return lambda: ConfigYamlScheduleStore(config_path=path)


def _one_shot(name="remind-once"):
    past = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    return ScheduleJob(
        name=name,
        message="ping",
        schedule=Schedule(kind="at", at=past),
        delete_after_run=True,
    )


def _statuses(store, job_id):
    return [r.status for r in store.get_history(job_id=job_id)]


def test_claim_keeps_one_shot_until_completion(make_store):
    store = make_store()
    job = _one_shot()
    store.add(job)
    claimed = store.claim_due(time.time(), owner_id="A", lease_seconds=300)
    assert [j.id for j in claimed] == [job.id]
    kept = make_store().get(job.id)
    assert kept is not None and kept._retiring == 1
    assert kept._lease_owner == "A"
    # A competitor cannot claim it while leased.
    assert make_store().claim_due(time.time(), owner_id="B") == []
    ScheduleRunner(store).mark_run(claimed[0])
    store.complete(job.id, "A")
    assert make_store().get(job.id) is None


def test_crashed_one_shot_is_retried_once(make_store):
    store = make_store()
    job = _one_shot()
    store.add(job)
    t0 = time.time()
    assert store.claim_due(t0, owner_id="A", lease_seconds=1)
    del store  # crash: no mark_run / complete

    restarted = make_store()
    retry = restarted.claim_due(t0 + 5, owner_id="B", lease_seconds=1)
    assert [j.id for j in retry] == [job.id]
    assert _statuses(restarted, job.id) == ["abandoned"]
    # Retry also crashes: logged and retired, never offered a third time.
    third = make_store()
    assert third.claim_due(t0 + 10, owner_id="C", lease_seconds=1) == []
    assert third.get(job.id) is None
    assert _statuses(make_store(), job.id) == ["abandoned", "abandoned"]


def test_retried_one_shot_completes_once(make_store):
    store = make_store()
    job = _one_shot()
    store.add(job)
    t0 = time.time()
    store.claim_due(t0, owner_id="A", lease_seconds=1)
    restarted = make_store()
    retry = restarted.claim_due(t0 + 5, owner_id="B", lease_seconds=300)
    ScheduleRunner(restarted).mark_run(retry[0])
    restarted.complete(job.id, "B")
    final = make_store()
    assert final.get(job.id) is None
    assert sorted(_statuses(final, job.id)) == ["abandoned", "succeeded"]


def test_crashed_recurring_job_logs_abandoned_and_waits_for_next_slot(make_store):
    store = make_store()
    job = ScheduleJob(
        name="hourly", message="digest",
        schedule=Schedule(kind="every", every_seconds=3600),
    )
    store.add(job)
    t0 = time.time()
    assert store.claim_due(t0, owner_id="A", lease_seconds=1)

    restarted = make_store()
    assert restarted.claim_due(t0 + 5, owner_id="B") == []
    assert _statuses(restarted, job.id) == ["abandoned"]
    assert restarted.get(job.id) is not None
    # Next slot fires normally.
    assert len(restarted.claim_due(t0 + 3601, owner_id="B")) == 1


def test_failed_one_shot_stays_listed_disabled(make_store):
    store = make_store()
    job = _one_shot()
    store.add(job)
    claimed = store.claim_due(time.time(), owner_id="A")
    ScheduleRunner(store).mark_run(claimed[0], status="failed", error="provider 503")
    store.complete(job.id, "A")
    after = make_store()
    kept = after.get(job.id)
    assert kept is not None and kept.enabled is False
    assert _statuses(after, job.id) == ["failed"]
    # Disabled: never re-claimed or silently retired.
    assert after.claim_due(time.time() + 10, owner_id="B") == []
    assert after.get(job.id) is not None


def test_one_shot_in_flight_past_lease_not_refired_by_same_process(make_store):
    store = make_store()
    job = _one_shot()
    store.add(job)
    t0 = time.time()
    assert store.claim_due(t0, owner_id="A", lease_seconds=1)
    # Same ticker polls again while its run is still going.
    assert store.claim_due(t0 + 5, owner_id="A", lease_seconds=1) == []
